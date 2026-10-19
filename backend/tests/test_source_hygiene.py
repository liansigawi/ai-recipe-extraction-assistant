"""Code files must not contain invisible bidirectional control characters.

They can make code display differently from how it runs ("Trojan Source"), and
they are easy to paste in by accident: Instagram captions can contain them.
Data files (fixtures, saved captions) may contain them; code writes them as
escape sequences instead.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html"}
SKIP_DIRS = {".venv", "node_modules", "data", ".git", "dist"}
BIDI_CONTROLS = {*range(0x200E, 0x2010), *range(0x202A, 0x202F), *range(0x2066, 0x206A)}


def test_no_bidi_control_characters_in_code():
    offenders = []
    for path in REPO.rglob("*"):
        if path.suffix not in CODE_SUFFIXES or SKIP_DIRS.intersection(path.relative_to(REPO).parts):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(ord(char) in BIDI_CONTROLS for char in line):
                offenders.append(f"{path.relative_to(REPO)}:{number}")
    assert not offenders, f"Write direction marks as escape sequences, not literal characters: {offenders}"
