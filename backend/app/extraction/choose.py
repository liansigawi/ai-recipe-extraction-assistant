"""Which model reads imported text (RECIPES_EXTRACTOR): the Claude API, or a local model.

    claude   the Claude API; needs ANTHROPIC_API_KEY; the text is sent to Anthropic
    ollama   a local model through Ollama; the text stays on this computer

Both give the same answer shape, and review.py checks both the same way.
"""

from app.config import Settings
from app.errors import ApiError
from app.extraction.claude import ClaudeExtractor, Extractor
from app.extraction.ollama import OllamaExtractor, ollama_problem
from app.schemas import ExtractionInfo


def extraction_info(settings: Settings) -> ExtractionInfo:
    """Can imports use the model right now? For the import screen; never includes the key."""
    if settings.extractor == "ollama":
        problem = ollama_problem(settings.ollama_url, settings.ollama_model)
        return ExtractionInfo(
            configured=problem is None, provider="ollama", model=settings.ollama_model, local=True, problem=problem
        )
    return ExtractionInfo(
        configured=settings.has_api_key,
        provider="claude",
        model=settings.model,
        local=False,
        problem=None if settings.has_api_key else "no_api_key",
    )


def make_extractor(settings: Settings) -> Extractor:
    if settings.extractor == "ollama":
        return OllamaExtractor(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
            context_tokens=settings.ollama_context_tokens,
            timeout=settings.ollama_timeout_seconds,
            mode=settings.extraction_mode,
        )
    if settings.anthropic_api_key is None or not settings.has_api_key:
        raise ApiError(
            503,
            "extraction_not_configured",
            "No Anthropic API key is configured on the backend. See the README, section 'Connect the Claude API'.",
        )
    return ClaudeExtractor(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.model,
        timeout=settings.model_timeout_seconds,
        mode=settings.extraction_mode,
    )
