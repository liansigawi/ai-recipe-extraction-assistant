"""The pasted text, cut into numbered passages that the model labels instead of copying.

A small model copying Hebrew can swap a word for a similar-sounding token ("מג׳הול" became
"מג׳ hollow": the model gave " hollow" 29% and the right "הול" 8%). So the model does not
retype the recipe: it says what each passage is (an ingredient, a step...), and the backend
copies the exact text.

Passages are lines, cut further where a line holds several sentences or a list:
- after a sentence end (". ", "! ", "? ", "… "), which stays with its sentence;
- after a label with a colon ("מצרכים: ...", "איך מכינים: ..."), the colon staying with the label;
- at the commas of a list that follows such a label ("מה צריך: כוס עדשים, כוס אורז, 3 בצלים").
Other commas and dashes do not cut: an ingredient line such as "1 (15 oz) can chickpeas,
drained and rinsed" or a step with " - " stays one passage (measured: cutting them led the model
to split one ingredient or step in two).
A piece with no letter (a list number "1.", an emoji) joins the next piece. Each passage keeps
its exact character positions in the original, so passages are copied back character for
character, separators included.
"""

import re
from dataclasses import dataclass

# Where a line is cut. Group "end" is the part that stays with the passage before the cut.
_CUT = re.compile(r"(?P<end>[.!?…]+[)\"'״”’]*|:)\s+")
_LIST_COMMA = re.compile(r"\s*[,;،]\s+")
_HAS_LETTER = re.compile(r"[^\W\d_]")  # a letter, in any script
_HAS_WORD = re.compile(r"[^\W_]")  # a letter or a digit
# List punctuation at the end of a copied item: separates items, is not part of the wording.
_TRAILING_SEPARATOR = re.compile(r"(?:\s*[,;:،]|\s+[-–—])+\s*$")
_LINE_BREAK = re.compile(r"[ \t]*\r?\n\s*")


@dataclass(frozen=True)
class Segment:
    id: int  # 1, 2, 3... in reading order
    line: int  # the line of the original text it is on
    start: int  # character positions in the original text
    end: int

    def text(self, source: str) -> str:
        return source[self.start : self.end]


def segment_text(source: str) -> list[Segment]:
    """The passages of a text, numbered from 1. The same text always gives the same passages."""
    segments: list[Segment] = []
    offset = 0
    for line_number, line in enumerate(source.splitlines(keepends=True)):
        content = line.rstrip("\r\n")
        pieces = _cut_line(content)
        for start, end in pieces:
            segments.append(Segment(id=len(segments) + 1, line=line_number, start=offset + start, end=offset + end))
        offset += len(line)
    return segments


def _cut_line(line: str) -> list[tuple[int, int]]:
    """(start, end) of each passage in one line, without surrounding spaces."""
    bounds: list[tuple[int, int]] = []
    position = 0
    after_label = False  # the piece follows "label:", so its commas separate list items
    for cut in _CUT.finditer(line):
        end = cut.start() + len(cut.group("end"))
        bounds += _list_items(line, position, end) if after_label else [(position, end)]
        after_label = cut.group("end") == ":"
        position = cut.end()
    bounds += _list_items(line, position, len(line)) if after_label else [(position, len(line))]

    passages: list[tuple[int, int]] = []
    carry: int | None = None  # start of a piece without words, waiting to join the next one
    for start, end in bounds:
        while start < end and line[start].isspace():
            start += 1
        while end > start and line[end - 1].isspace():
            end -= 1
        if start == end:
            continue
        if carry is not None:
            start, carry = carry, None
        if _HAS_LETTER.search(line[start:end]):
            passages.append((start, end))
        else:
            carry = start  # "1.", "2)", an emoji: belongs to the passage that follows
    if carry is not None:
        end = len(line.rstrip())
        if passages:  # at the end of the line: join the last passage
            passages[-1] = (passages[-1][0], end)
        elif _HAS_WORD.search(line[carry:end]):  # a line of only digits ("12") is still a passage
            passages.append((carry, end))
    return passages


def _list_items(line: str, start: int, end: int) -> list[tuple[int, int]]:
    """A piece after a label, cut at its commas (the items of a list)."""
    bounds = []
    for comma in _LIST_COMMA.finditer(line, start, end):
        bounds.append((start, comma.start()))
        start = comma.end()
    return [*bounds, (start, end)]


def passage_text(source: str, segments: list[Segment], first: int, last: int) -> str:
    """The exact text of passages first..last (numbers from 1): the original characters from the
    first passage to the last, separators included; a line break inside becomes one space.
    Ends without list punctuation (",", ":", " -")."""
    span = source[segments[first - 1].start : segments[last - 1].end]
    return _TRAILING_SEPARATOR.sub("", _LINE_BREAK.sub(" ", span))


KEY_LENGTH = 50  # characters of a passage's opening words in its key


def passage_key(source: str, segment: Segment) -> str:
    """How the answer names a passage: its number and opening words ("[5] שוט אספרסו").

    The answer's schema lists these keys in order, and Ollama and the Claude API write them for
    the model: it cannot skip a passage, and labels each one with that passage's own words in view.
    """
    text = segment.text(source)
    return f"[{segment.id}] {text if len(text) <= KEY_LENGTH else text[:KEY_LENGTH] + '…'}"


def ends_with_colon(source: str, segment: Segment) -> bool:
    """A label such as "מצרכים:" or "איך מכינים:": a heading, not an ingredient or a step."""
    rest = source[segment.end :].split("\n", 1)[0]
    return source[segment.start : segment.end].rstrip().endswith(":") or rest.lstrip().startswith(":")


def render_segments(source: str, segments: list[Segment]) -> str:
    """The text as the model sees it: each line as written, with [n] before each passage.

    Lines without passages (empty, or only symbols) stay as they are, so paragraphs are visible.
    """
    lines = source.splitlines()
    starts: dict[int, list[Segment]] = {}
    for segment in segments:
        starts.setdefault(segment.line, []).append(segment)
    line_offsets = []
    offset = 0
    for line in source.splitlines(keepends=True):
        line_offsets.append(offset)
        offset += len(line)
    rendered = []
    for number, line in enumerate(lines):
        for segment in reversed(starts.get(number, [])):
            at = segment.start - line_offsets[number]
            line = f"{line[:at]}[{segment.id}] {line[at:]}"
        rendered.append(line)
    return "\n".join(rendered)
