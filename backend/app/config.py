"""Application settings that come from the environment.

Milestone 1 only needs the data directory. Later milestones add the database
URL, model settings and the API key here.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Local data folder (database, uploads, probe output). Git-ignored by default.

    Override with the RECIPES_DATA_DIR environment variable, for example to keep
    recipes in a folder that your backup tool already covers. It must be a full
    path: a relative one would depend on the current folder and could land data
    somewhere git does not ignore.
    """
    value = os.environ.get("RECIPES_DATA_DIR")
    if not value:
        return (REPO_ROOT / "data").resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"RECIPES_DATA_DIR must be a full path, such as D:/Backups/recipe-notebook (got {value!r}).")
    return path.resolve()
