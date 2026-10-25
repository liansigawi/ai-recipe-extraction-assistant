"""The instructions' examples never come from the evaluation cases, so the quality check measures how
the model handles text it was not shown (and a case does not pass because its own line is an example)."""

import re

from app.extraction.output import ExtractionOutput, ReferenceOutput
from app.extraction.prompt import REFERENCE_SYSTEM_PROMPT, SYSTEM_PROMPT
from app.extraction.review import normalize
from evals.run_extraction import CASES_DIR

DOUBLE_QUOTED = re.compile(r'"([^"\n]{2,})"')  # the prompts quote their examples like this
SINGLE_QUOTED = re.compile(r"(?<!\w)'([^'\n]{1,60})'(?!\w)")  # the schema's descriptions like this


def examples(text: str, quoted: re.Pattern = DOUBLE_QUOTED) -> list[str]:
    """Quoted examples with Hebrew in them, or of two words or more (field and role names are one word)."""
    return [e for e in quoted.findall(text) if re.search("[א-ת]", e) or len(e.split()) >= 2]


def descriptions(node) -> str:
    """Every field description of a JSON schema, one per line."""
    if isinstance(node, dict):
        own = [node["description"]] if isinstance(node.get("description"), str) else []
        return "\n".join(own + [descriptions(value) for value in node.values()])
    if isinstance(node, list):
        return "\n".join(descriptions(item) for item in node)
    return ""


def test_no_example_in_the_instructions_or_the_answer_format_is_taken_from_an_evaluation_case():
    cases = {path.stem: normalize(path.read_text(encoding="utf-8")).lower() for path in CASES_DIR.glob("*.txt")}
    schema_text = descriptions([ExtractionOutput.model_json_schema(), ReferenceOutput.model_json_schema()])
    sources = {
        "text prompt": examples(SYSTEM_PROMPT),
        "reference prompt": examples(REFERENCE_SYSTEM_PROMPT),
        "answer schemas": examples(schema_text, SINGLE_QUOTED),
    }
    assert all(sources.values()), "each source has examples to check"
    reused = [
        f"{where}: {example!r} is in case {name}"
        for where, found in sources.items()
        for example in found
        for name, case in cases.items()
        if normalize(example).lower() in case
    ]
    assert reused == []
