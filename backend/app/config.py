"""Application settings, read from environment variables or the repository's .env file.

Every setting uses the prefix RECIPES_ (for example RECIPES_DATA_DIR). A real
environment variable wins over the same line in .env. See .env.example.
"""

from pathlib import Path
from typing import Any

from pydantic import ValidationError, field_validator
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


def data_dir() -> Path:
    """The data folder, read fresh from the environment and .env each time.

    Raises ValueError with a one-line, human-readable message for a bad setting.
    """
    try:
        return Settings().data_dir
    except ValidationError as exc:
        raise ValueError("; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())) from None
