"""Application settings, read from environment variables or the repository's .env file.

Every setting uses the prefix RECIPES_ (for example RECIPES_DATA_DIR), except the
Anthropic API key, which uses its standard name ANTHROPIC_API_KEY. A real environment
variable wins over the same line in .env. See .env.example.
"""

from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RECIPES_",
        env_file=REPO_ROOT / ".env",  # an absolute path, so it works from any working folder
        env_file_encoding="utf-8",
        extra="ignore",  # .env may also hold settings for other tools
    )

    # Local data folder: database, uploads, probe output. Git-ignored by default.
    data_dir: Path = REPO_ROOT / "data"
    # Print every SQL statement the backend runs (RECIPES_SQL_ECHO=true): handy for learning.
    sql_echo: bool = False

    # The key for the Claude API. SecretStr: printed as '**********', never as the key itself.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "RECIPES_ANTHROPIC_API_KEY")
    )
    # The Claude model that reads imported text (RECIPES_MODEL), and how long one request may take.
    model: str = "claude-opus-5-5"
    model_timeout_seconds: float = Field(default=120, gt=0, le=600)

    # Who reads imported text (RECIPES_EXTRACTOR): "claude" (the Claude API) or "ollama" (a local
    # model on this computer, through Ollama). See app/extraction/choose.py.
    extractor: Literal["claude", "ollama"] = "claude"
    # How the model answers (RECIPES_EXTRACTION_MODE): "references" labels numbered passages of
    # the original, which the backend copies exactly; "text" retypes the wording (the first
    # approach, kept for comparison). See app/extraction/segments.py.
    extraction_mode: Literal["references", "text"] = "references"
    # The local model and Ollama's address. The address must be this computer: the import screen
    # tells the person that their text stays here.
    ollama_model: str = "qwen3:8b"
    ollama_url: str = "http://127.0.0.1:11434"
    # The model's working memory for one import, in tokens: the rules, the categories, the text
    # and the answer must all fit. Ollama's default (4k on GPUs under 24 GB) is too small: a long
    # Hebrew caption needed about 4,850. 8k keeps qwen3:8b entirely on an 8 GB GPU (6.2 GB, measured
    # on an RTX 5060 Laptop); more spills part of the model to the CPU, which is slower.
    ollama_context_tokens: int = Field(default=8_192, ge=4_096, le=131_072)
    # A local model is slower than the API, especially the first time (it is loaded into memory).
    ollama_timeout_seconds: float = Field(default=600, gt=0, le=3_600)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "recipes.db"

    @property
    def has_api_key(self) -> bool:
        return self.anthropic_api_key is not None and self.anthropic_api_key.get_secret_value().strip() != ""

    @property
    def extraction_model(self) -> str:
        """The model imports use, whichever extractor is chosen."""
        return self.ollama_model if self.extractor == "ollama" else self.model

    @field_validator("ollama_url")
    @classmethod
    def _ollama_on_this_computer(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or parts.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "RECIPES_OLLAMA_URL must point to this computer (for example http://127.0.0.1:11434), "
                "so the text of your recipes stays here"
            )
        return value.strip().rstrip("/")

    @field_validator("data_dir", mode="before")
    @classmethod
    def _empty_means_default(cls, value: Any) -> Any:
        return REPO_ROOT / "data" if value in (None, "") else value

    @field_validator("data_dir")
    @classmethod
    def _must_be_full_path(cls, value: Path) -> Path:
        # In a .env file, "D:\Backups\recipes" in double quotes turns "\r" into a hidden control character.
        if any(ord(char) < 32 for char in str(value)):
            raise ValueError(
                "RECIPES_DATA_DIR contains a hidden control character. In .env, write the path with forward "
                "slashes and no quotes, e.g. RECIPES_DATA_DIR=D:/Backups/recipe-notebook"
            )
        # A relative path would depend on the current folder and could put data where git does not ignore it.
        path = value.expanduser()
        if not path.is_absolute():
            raise ValueError(f"RECIPES_DATA_DIR must be a full path, such as D:/Backups/recipe-notebook (got {str(value)!r})")
        return path.resolve()


def load_settings() -> Settings:
    """Settings read fresh from the environment and .env.

    Raises ValueError with a one-line, human-readable message for a bad setting.
    """
    try:
        return Settings()
    except ValidationError as exc:
        raise ValueError("; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())) from None


def data_dir() -> Path:
    """The data folder, read fresh from the environment and .env each time."""
    return load_settings().data_dir
