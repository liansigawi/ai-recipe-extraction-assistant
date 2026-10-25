"""Reading pasted text with a local model through Ollama, instead of the Claude API.

The same job and the same answer shape as claude.py: the rules, the categories and the text go
in; a ReferenceOutput (or, in text mode, an ExtractionOutput) comes out, and review.py checks it
exactly like Claude's answers. The
text never leaves this computer: Ollama runs here, and the address must be 127.0.0.1 or
localhost (app/config.py).

Ollama's chat API (https://docs.ollama.com/api/chat): `format` takes the JSON schema and keeps
the model's answer in that shape; `options.num_ctx` sets the model's working memory in tokens.
"""

import json
import logging
import time
from typing import Any

import httpx2
from pydantic import ValidationError

from app import schemas
from app.errors import ApiError
from app.extraction.output import ClassificationAnswer, ExtractionOutput, ReferenceOutput
from app.extraction.prompt import ModelRequest, build_classification_request, build_request
from app.extraction.review import is_recipe, make_draft

log = logging.getLogger("uvicorn.error")

# Ollama keeps the answer in the schema's shape, but unlike the Claude API it does not show the
# model what each field means. So the schema, with its descriptions, is also in the instructions.
# Asking for compact JSON (no line breaks or indents) was tried and dropped: about 30% faster, but
# measured on the 20 cases it made worse choices (quantities wrong 16 times instead of 11, and in
# text mode a caption whose every quantity became its whole line).
SCHEMA_INTRO = (
    "\n\nANSWER FORMAT\n"
    "Answer with one JSON object that follows this JSON schema. The descriptions explain each field.\n"
)


class OllamaExtractor:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        context_tokens: int,
        timeout: float,
        mode: str = "references",
        client: httpx2.Client | None = None,
    ) -> None:
        self.model = model
        self.mode = mode  # "references" (labeled passages) or "text" (copied wording)
        self._base_url = base_url
        self._context_tokens = context_tokens
        self._timeout = timeout
        self._client = client  # tests pass one with a fake transport
        self.last_usage: dict[str, int] = {}  # tokens of the latest request, for the quality check
        self.last_raw: str | None = None  # the model's answer exactly as received, for tracing

    def extract(self, text: str, categories: list[schemas.Category]) -> ExtractionOutput | ReferenceOutput:
        self.last_usage = {}
        self.last_raw = None
        request = build_request(text, categories, self.mode)
        self.last_raw = self._chat(request, len(text))
        answer_type = ReferenceOutput if request.mode == "references" else ExtractionOutput
        try:
            output = answer_type.model_validate_json(self.last_raw)
        except ValidationError:
            raise ApiError(502, "extraction_invalid_output", "The local model's answer did not have the expected shape.") from None
        if isinstance(output, ReferenceOutput) and is_recipe(output):
            output = self._classify(output, text, categories)
        return output

    def _classify(self, output: ReferenceOutput, text: str, categories: list[schemas.Category]) -> ReferenceOutput:
        """Ask for the category again, from the finished draft alone (a separate, short request).
        If that request fails, the first answer's classification stays."""
        request = build_classification_request(make_draft(output, text, categories), categories)
        try:
            answer = ClassificationAnswer.model_validate_json(self._chat(request, len(text)))
        except (ApiError, ValidationError) as error:
            log.warning("Classification request failed (%s); keeping the first answer's category.", error)
            return output
        return output.model_copy(update={"classification": answer.classification, "dish": answer.dish})

    def _chat(self, request: ModelRequest, characters: int) -> str:
        """One request to the model, its answer as text. Tokens add up in last_usage."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system + SCHEMA_INTRO + json.dumps(_for_prompt(request.schema), ensure_ascii=False)},
                {"role": "user", "content": request.user},
            ],
            "format": request.schema,
            "stream": False,
            # Stop at the end of the working memory. By default Ollama then drops the oldest half
            # (the instructions and the text) and goes on: a model repeating itself once ran for
            # 28,000 tokens, until the timeout, instead of stopping at 8,192.
            "shift": False,
            # temperature 0: the most likely words, as close to copying as a model gets.
            "options": {"num_ctx": self._context_tokens, "temperature": 0},
        }
        if "thinking" in self._capabilities():
            body["think"] = False  # a reasoning model would spend its working memory thinking aloud

        started = time.monotonic()
        data = self._send("POST", "/api/chat", body, self._timeout).json()
        prompt_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)
        self.last_usage = {
            "input_tokens": self.last_usage.get("input_tokens", 0) + prompt_tokens,
            "output_tokens": self.last_usage.get("output_tokens", 0) + output_tokens,
        }
        log.info(
            "Ollama %s, %s: %d characters in, %s prompt and %s output tokens (of %d), %.1f s, stop: %s",
            self.model, request.mode, characters, prompt_tokens, output_tokens, self._context_tokens,
            time.monotonic() - started, data.get("done_reason"),
        )
        if data.get("done_reason") == "length" or prompt_tokens + output_tokens >= self._context_tokens:
            raise self._out_of_memory()
        try:
            return data["message"]["content"]
        except (KeyError, TypeError):
            raise ApiError(502, "extraction_invalid_output", "The local model's answer did not have the expected shape.") from None

    def _capabilities(self) -> list[str]:
        """What the model can do ("completion", "thinking", "vision"...); empty if Ollama cannot say."""
        try:
            response = self._send("POST", "/api/show", {"model": self.model}, 30)
        except ApiError as error:
            if error.code == "extraction_model_missing":
                raise
            return []
        return list(response.json().get("capabilities") or [])

    def _send(self, method: str, path: str, body: dict[str, Any], timeout: float) -> httpx2.Response:
        response = self._request(method, path, body, timeout)
        if response.status_code >= 500 and path == "/api/chat":
            # Ollama's GPU runner crashed twice in about 350 requests ("CUDA error: unknown error");
            # the next request reloads the model and works, so one more try spares the person an error.
            log.warning("Ollama answered HTTP %s; trying once more.", response.status_code)
            response = self._request(method, path, body, timeout)
        if response.status_code == 404:
            raise ApiError(
                503, "extraction_model_missing", f"Ollama does not have the model {self.model}. Run: ollama pull {self.model}"
            )
        if response.status_code == 400 and "context" in response.text:  # the text alone does not fit
            raise self._out_of_memory()
        if response.status_code != 200:
            raise ApiError(502, "extraction_failed", f"Ollama answered with an error (HTTP {response.status_code}).")
        return response

    def _request(self, method: str, path: str, body: dict[str, Any], timeout: float) -> httpx2.Response:
        try:
            if self._client is not None:
                return self._client.request(method, self._base_url + path, json=body, timeout=timeout)
            with new_client() as client:
                return client.request(method, self._base_url + path, json=body, timeout=timeout)
        except httpx2.TimeoutException:
            raise ApiError(
                504, "extraction_timeout", "The local model did not answer in time (RECIPES_OLLAMA_TIMEOUT_SECONDS)."
            ) from None
        except httpx2.HTTPError:
            raise ApiError(
                503, "extraction_local_unavailable", "Ollama is not running on this computer. Start the Ollama app."
            ) from None

    def _out_of_memory(self) -> ApiError:
        return ApiError(
            502,
            "extraction_incomplete",
            f"The local model's working memory ({self._context_tokens} tokens) filled up before it finished: the "
            "text is too long, or the model repeated itself. Try again, paste only the recipe, or raise "
            "RECIPES_OLLAMA_CONTEXT_TOKENS.",
        )


def ollama_problem(base_url: str, model: str, client: httpx2.Client | None = None) -> str | None:
    """None if Ollama is running and has the model; otherwise what is wrong, for the import screen."""
    try:
        if client is not None:
            response = client.get(base_url + "/api/tags", timeout=3)
        else:
            with new_client() as own:
                response = own.get(base_url + "/api/tags", timeout=3)
    except httpx2.HTTPError:
        return "ollama_unreachable"
    if response.status_code != 200:
        return "ollama_unreachable"
    names = {
        _full_name(name)
        for entry in response.json().get("models") or []
        for name in (entry.get("name"), entry.get("model"))
        if name
    }
    return None if _full_name(model) in names else "ollama_model_missing"


def new_client() -> httpx2.Client:
    """Every connection to Ollama starts here (tests replace it, so none can reach a real Ollama)."""
    return httpx2.Client()


def _full_name(name: str) -> str:
    """"qwen3" and "qwen3:latest" are the same model in Ollama."""
    return name if ":" in name else f"{name}:latest"


def _for_prompt(schema: dict[str, Any]) -> Any:
    """The schema as written into the instructions: without "title" labels, with long lists of
    allowed numbers (passage numbers) shortened to "1 to N", and the passages' keys left out (they
    would repeat the whole text once more; the model sees them as it writes, from `format`).
    `format` still enforces the full schema."""
    schema = _short_number_lists(_without_titles(schema))
    passages = schema.get("properties", {}).get("passages")
    if isinstance(passages, dict) and "properties" in passages:
        schema["properties"]["passages"] = {
            "type": "object",
            "description": passages.get("description", ""),
            "additionalProperties": {"$ref": "#/$defs/PassageRole"},
        }
    return schema


def _short_number_lists(node: Any) -> Any:
    if isinstance(node, dict):
        values = node.get("enum")
        if isinstance(values, list) and len(values) > 12 and all(isinstance(v, int) for v in values):
            shortened = {key: value for key, value in node.items() if key != "enum"}
            shortened["description"] = (shortened.get("description", "") + f" A number from {min(values)} to {max(values)}.").strip()
            return shortened
        return {key: _short_number_lists(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_short_number_lists(item) for item in node]
    return node


def _without_titles(node: Any, names: bool = False) -> Any:
    """The schema without its "title" labels, which only repeat the field names.

    Careful: inside "properties" (and "$defs") the keys are names, and the recipe has a field
    that is really called "title"; those are kept. `names` says that this dict is such a map.
    """
    if isinstance(node, dict):
        return {
            key: _without_titles(value, names=not names and key in ("properties", "$defs"))
            for key, value in node.items()
            if names or key != "title"
        }
    if isinstance(node, list):
        return [_without_titles(item) for item in node]
    return node
