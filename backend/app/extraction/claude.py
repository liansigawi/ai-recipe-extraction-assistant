"""The call to the Claude API: pasted text in, ExtractionOutput out, or a clear error.

One request per import, with a bounded answer length and timeout. The API key is passed in
by the caller (from the backend's settings) and never logged or sent anywhere but Anthropic.
"""

import logging
import time
from typing import Any, Protocol

import anthropic
from pydantic import ValidationError

from app import schemas
from app.errors import ApiError
from app.extraction.output import ExtractionOutput, output_schema
from app.extraction.prompt import SYSTEM_PROMPT, build_user_message

log = logging.getLogger("uvicorn.error")

# The longest answer we accept, in tokens (roughly: a token is a short word or part of one;
# Hebrew uses more of them). A long recipe needs a few thousand; this leaves ample room.
MAX_OUTPUT_TOKENS = 16_000


class Extractor(Protocol):
    """What the import endpoint needs. Tests pass a stand-in with the same two members."""

    model: str

    def extract(self, text: str, categories: list[schemas.Category]) -> ExtractionOutput: ...


class ClaudeExtractor:
    def __init__(self, *, api_key: str, model: str, timeout: float, client: Any = None) -> None:
        self.model = model
        # max_retries: the SDK retries connection errors, rate limits and server errors twice,
        # waiting a little longer each time.
        self._client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    def extract(self, text: str, categories: list[schemas.Category]) -> ExtractionOutput:
        started = time.monotonic()
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(text, categories)}],
                # Structured output: the answer must follow this JSON schema.
                output_config={"format": {"type": "json_schema", "schema": output_schema(categories)}},
            )
        except anthropic.AuthenticationError:
            raise ApiError(
                502, "extraction_auth_failed", "The Claude API did not accept the API key. Check ANTHROPIC_API_KEY."
            ) from None
        except anthropic.PermissionDeniedError:
            raise ApiError(
                502, "extraction_auth_failed", f"The API key may not use the model {self.model}. Check RECIPES_MODEL."
            ) from None
        except anthropic.NotFoundError:
            raise ApiError(502, "extraction_failed", f"The Claude API does not know the model {self.model}.") from None
        except anthropic.RateLimitError:
            raise ApiError(503, "extraction_busy", "The Claude API is limiting requests right now. Try again soon.") from None
        except anthropic.APITimeoutError:  # before APIConnectionError: it is a kind of connection error
            raise ApiError(504, "extraction_timeout", "The Claude API did not answer in time.") from None
        except anthropic.APIConnectionError:
            raise ApiError(502, "extraction_unreachable", "Could not reach the Claude API. Check the internet connection.") from None
        except anthropic.APIStatusError as error:
            if error.status_code in (503, 529):  # unavailable / overloaded: temporary
                raise ApiError(503, "extraction_busy", "The Claude API is overloaded right now. Try again soon.") from None
            raise ApiError(502, "extraction_failed", f"The Claude API answered with an error (HTTP {error.status_code}).") from None

        usage = response.usage
        log.info(
            "Extraction with %s: %d characters in, %s input and %s output tokens, %.1f s, stop: %s",
            self.model, len(text), usage.input_tokens, usage.output_tokens, time.monotonic() - started, response.stop_reason,
        )
        if response.stop_reason == "refusal":
            raise ApiError(502, "extraction_refused", "Claude declined to process this text.")
        if response.stop_reason in ("max_tokens", "model_context_window_exceeded"):
            raise ApiError(502, "extraction_incomplete", "Claude's answer was cut off before the end.")

        answer = "".join(block.text for block in response.content if block.type == "text")
        try:
            return ExtractionOutput.model_validate_json(answer)
        except ValidationError:
            raise ApiError(502, "extraction_invalid_output", "Claude's answer did not have the expected shape.") from None
