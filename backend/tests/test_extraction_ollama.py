"""The local extractor (app/extraction/ollama.py): what it sends to Ollama, and how it handles answers.

A fake connection (httpx2.MockTransport) answers like Ollama and records the requests, so no
real Ollama is needed (conftest.py also blocks real connections).
"""

import json
import re

import httpx2
import pytest

from app.config import Settings
from app.errors import ApiError
from app.extraction.ollama import SCHEMA_INTRO, OllamaExtractor, ollama_problem
from app.extraction.output import direct_classification_schema, output_schema
from app.extraction.prompt import CLASSIFY_DIRECT_SYSTEM_PROMPT, DESCRIBE_DISH, SYSTEM_PROMPT, build_classification_request
from app.schemas import Category, RecipeInput
from tests.test_extraction_claude import ANSWER

CATEGORIES = [Category(id=1, name="קינוחים"), Category(id=3, name="ארוחות קלילות")]
URL = "http://127.0.0.1:11434"


def fake_ollama(*, capabilities=("completion", "thinking"), chat=None, status=200, error=None):
    """A fake connection, and the list of requests it received."""
    requests: list[tuple[str, dict]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content) if request.content else {}
        requests.append((request.url.path, body))
        if error is not None:
            raise error
        if request.url.path == "/api/show":
            return httpx2.Response(status, json={"capabilities": list(capabilities)})
        if request.url.path == "/api/chat":
            reply = {
                "message": {"role": "assistant", "content": json.dumps(ANSWER, ensure_ascii=False)},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 3000,
                "eval_count": 800,
            }
            return httpx2.Response(status, json=reply | (chat or {}))
        return httpx2.Response(404, json={"error": "not found"})

    return httpx2.Client(transport=httpx2.MockTransport(handle)), requests


def extractor(client: httpx2.Client, context: int = 12_288, mode: str = "text") -> OllamaExtractor:
    return OllamaExtractor(base_url=URL, model="qwen3:8b", context_tokens=context, timeout=60, mode=mode, client=client)


def test_the_request_has_the_rules_the_schema_and_the_text_as_data():
    client, requests = fake_ollama()
    output = extractor(client).extract("חביתה\n2 ביצים", CATEGORIES)

    assert output.title == "חביתה"
    [(show_path, show), (chat_path, chat)] = requests
    assert (show_path, show) == ("/api/show", {"model": "qwen3:8b"})
    assert chat_path == "/api/chat"
    assert chat["model"] == "qwen3:8b"
    assert chat["stream"] is True  # read piece by piece, the clock checked at each (time asleep counts)
    assert chat["think"] is False  # this model can think; for extraction it should not
    assert chat["options"] == {"num_ctx": 12_288, "temperature": 0}
    assert chat["shift"] is False  # stop when the working memory is full, never drop the instructions
    assert chat["format"] == output_schema(CATEGORIES)  # the same schema as for Claude, ids limited
    system, user = chat["messages"]
    assert system["role"] == "system" and system["content"].startswith(SYSTEM_PROMPT + SCHEMA_INTRO)
    shown_schema = json.loads(system["content"].removeprefix(SYSTEM_PROMPT + SCHEMA_INTRO))
    # The "title" labels are gone, but the recipe's own title field is there, with its description.
    assert '"title": "' not in json.dumps(shown_schema)
    assert "composed it" in shown_schema["properties"]["title_written_in_text"]["description"]
    assert "title as written" in shown_schema["properties"]["title"]["description"]
    assert set(shown_schema["$defs"]) == set(chat["format"]["$defs"])
    assert user["role"] == "user" and "\nחביתה\n2 ביצים\n</source_text_" in user["content"]


def test_a_model_that_cannot_think_is_not_asked_about_it():
    client, requests = fake_ollama(capabilities=("completion",))
    extractor(client).extract("חביתה", CATEGORIES)
    assert "think" not in requests[-1][1]


@pytest.mark.parametrize(
    ("chat", "code"),
    [
        ({"done_reason": "length"}, "extraction_incomplete"),
        ({"prompt_eval_count": 11_000, "eval_count": 1_288}, "extraction_incomplete"),  # filled the working memory
        ({"message": {"role": "assistant", "content": '{"is_recipe": true, "title": "cut'}}, "extraction_invalid_output"),
        ({"message": {"role": "assistant", "content": "{}"}}, "extraction_invalid_output"),
    ],
)
def test_an_unusable_answer_is_a_clear_error(chat, code):
    client, _ = fake_ollama(chat=chat)
    with pytest.raises(ApiError) as caught:
        extractor(client).extract("חביתה", CATEGORIES)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("fake", "status", "code"),
    [
        (dict(error=httpx2.ConnectError("refused")), 503, "extraction_local_unavailable"),
        (dict(error=httpx2.ReadTimeout("slow")), 504, "extraction_timeout"),
        (dict(status=404), 503, "extraction_model_missing"),
        (dict(status=500, capabilities=()), 502, "extraction_failed"),
    ],
)
def test_ollama_failures_become_clear_errors(fake, status, code):
    client, _ = fake_ollama(**fake)
    with pytest.raises(ApiError) as caught:
        extractor(client).extract("חביתה", CATEGORIES)
    assert (caught.value.status_code, caught.value.code) == (status, code)


def test_a_text_too_long_for_the_working_memory_is_reported_as_such():
    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/show":
            return httpx2.Response(200, json={"capabilities": ["completion"]})
        message = "request (16919 tokens) exceeds the available context size (8192 tokens), try increasing it"
        return httpx2.Response(400, json={"error": message})

    with pytest.raises(ApiError) as caught:
        extractor(httpx2.Client(transport=httpx2.MockTransport(handle))).extract("חביתה", CATEGORIES)
    assert caught.value.code == "extraction_incomplete" and "too long" in caught.value.message


OMELETTE = RecipeInput(
    title="חביתה", ingredient_groups=[{"ingredients": [{"text": "2 ביצים"}]}], step_groups=[{"steps": ["מטגנים."]}]
)


def test_a_finished_draft_is_classified_without_a_description_of_the_dish_first():
    answer = {"classification": {"fit": "clear", "category_id": 3, "subcategory_id": None, "candidate_category_ids": []}}
    client, requests = fake_ollama(chat={"message": {"role": "assistant", "content": json.dumps(answer)}})
    classification = extractor(client, mode="references").classify_draft(OMELETTE, CATEGORIES)

    assert classification.category_id == 3
    chat = requests[-1][1]
    assert chat["format"] == direct_classification_schema(CATEGORIES) and "dish" not in chat["format"]["properties"]
    system, user = chat["messages"]
    assert system["content"].startswith(CLASSIFY_DIRECT_SYSTEM_PROMPT + SCHEMA_INTRO) and DESCRIBE_DISH not in system["content"]
    assert "\nחביתה\n\n2 ביצים\n\nמטגנים.\n</source_text_" in user["content"]


def test_the_local_request_is_the_claude_api_s_without_the_description_of_the_dish():
    # Exactly the candidate measured on 2026-11-05: one sentence and one answer field fewer, nothing else.
    described = build_classification_request(OMELETTE, CATEGORIES)
    direct = build_classification_request(OMELETTE, CATEGORIES, describe_dish=False)
    assert described.system.count(DESCRIBE_DISH) == 1 and direct.system == described.system.replace(DESCRIBE_DISH, "")
    properties = {name: value for name, value in described.schema["properties"].items() if name != "dish"}
    assert direct.schema == {**described.schema, "properties": properties, "required": ["classification"]}
    tag = re.compile(r"source_text_[0-9a-f]+")
    assert tag.sub("tag", direct.user) == tag.sub("tag", described.user)


def tags(*names: str) -> httpx2.Client:
    models = [{"name": name, "model": name} for name in names]
    return httpx2.Client(transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json={"models": models})))


def test_the_import_screen_learns_whether_ollama_is_ready():
    assert ollama_problem(URL, "qwen3:8b", client=tags("qwen3:8b", "gemma4:e4b")) is None
    assert ollama_problem(URL, "qwen3", client=tags("qwen3:latest")) is None  # the same model
    assert ollama_problem(URL, "qwen3:8b", client=tags("qwen3:4b")) == "ollama_model_missing"
    down = httpx2.Client(transport=httpx2.MockTransport(lambda request: (_ for _ in ()).throw(httpx2.ConnectError("x"))))
    assert ollama_problem(URL, "qwen3:8b", client=down) == "ollama_unreachable"


@pytest.mark.parametrize("url", ["http://192.168.1.20:11434", "https://ollama.example.com", "ftp://127.0.0.1:11434"])
def test_ollama_must_run_on_this_computer(url):
    with pytest.raises(Exception, match="must point to this computer"):
        Settings(_env_file=None, ollama_url=url)
    assert Settings(_env_file=None, ollama_url="http://localhost:11434/").ollama_url == "http://localhost:11434"
