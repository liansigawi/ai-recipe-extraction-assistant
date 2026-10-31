"""The quantity of an ingredient line: the span of the line that holds its amount.

The rules are in docs/quantity-conventions.md. The span is cut from the line, never written:
"3 כוסות" from "3 כוסות קמח לבן", "אחד" from "בצל אחד גדול", "חצי" from "מיץ מחצי לימון", and
None from "מלח ופלפל". Nothing is converted or normalized, so scaling can later replace just this
span. The model only decides which passages are ingredients; reading the amount is done here, the
same way every time (measured: when the model chose the quantity itself, 26 of 143 were wrong).
"""

import re

_PREFIX = "ומבלכשה"  # Hebrew letters that attach to a word: "מחצי" is "from half"

_NUMBER = r"\d+(?:[.,]\d+)?(?:\s*[½¼¾⅓⅔⅛])?|[½¼¾⅓⅔⅛]"
_FRACTION = r"\d+\s*/\s*\d+"
_DIGITS = rf"(?:\d+\s+\d+\s*/\s*\d+|{_FRACTION}|{_NUMBER})"
_HEBREW_NUMBERS = (
    "אחד|אחת|שניים|שנים|שתיים|שתים|שני|שתי|שלושה|שלוש|שלושת|ארבעה|ארבע|ארבעת|חמישה|חמש|חמשת|שישה|שש|ששת|"
    "שבעה|שבע|שבעת|שמונה|שמונת|תשעה|תשע|תשעת|עשרה|עשר|עשרת"
)
_HEBREW_FRACTIONS = "שלושת רבעי|שני שלישי|חצי|רבע|שליש"
_ENGLISH_NUMBERS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|half|a half|a quarter|quarter"
_WORD_AMOUNTS = "קצת|מעט|a little|a pinch|a handful|a dash|a splash"
_AND_A_HALF = r"(?:\s*(?:וחצי|ורבע|and a half))?"

_HEBREW_UNITS = (
    "כוסות|כוסית|כוס|כפות|כפיות|כפית|כף|גרמים|גרם|גר׳|גר'|גר’|גר|ג׳|ג'|ק״ג|ק\"ג|קג|קילוגרם|קילו|ליטרים|ליטר|"
    "מ״ל|מ\"ל|מל׳|מל'|מל’|מיליליטר|מל|קורטוב|קורט|חופנים|חופן|צרורות|צרור|שיני|שן|פרוסות|פרוסת|פרוסה|"
    "חתיכות|חתיכת|חתיכה|קוביות|קוביית|קוביה|ענפים|ענפי|ענף|גבעולי|גבעולים|גבעול|פחיות|פחית|קופסאות|קופסת|קופסה|"
    "חבילות|חבילת|חבילה|שקיות|שקית|שקיקים|שקיק|צנצנות|צנצנת|שוטים|שוט|מקלות|מקל|ראשי|ראש|יחידות|יחידה"
)
_ENGLISH_UNITS = (
    r"cups?|tablespoons?|tbsps?\.?|tbs\.?|teaspoons?|tsps?\.?|grams?|g|kgs?|kilograms?|ml|millilit(?:er|re)s?|"
    r"lit(?:er|re)s?|l|oz\.?|ounces?|lbs?\.?|pounds?|pinch(?:es)?|handfuls?|cloves?|cans?|tins?|packages?|pkgs?\.?|"
    r"packets?|slices?|pieces?|sprigs?|bunch(?:es)?|sticks?|jars?|dash(?:es)?|quarts?|pints?|heads?"
)
_MODIFIERS = "גדושות|גדושה|שטוחות|שטוחה|מלאות|מלאה|heaped|heaping|level|rounded|scant"
_UNIT = rf"(?:{_HEBREW_UNITS}|{_ENGLISH_UNITS})(?:\s+(?:{_MODIFIERS}))?"
# A size, a percentage or a temperature after a number: not an amount ("38%", "2 ס״מ").
_NOT_AN_AMOUNT = re.compile(r"\s*(?:%|ס״מ|ס\"מ|ס'מ|ס”מ|ס״מ|מ״מ|cm|mm|inch|in\.|אינץ|°|מעלות)", re.IGNORECASE)

_AMOUNT = (
    rf"(?:{_DIGITS})(?:\s*(?:[-–—]|עד|to|or|או)\s*(?:{_DIGITS}))?{_AND_A_HALF}"
    rf"|(?:{_HEBREW_FRACTIONS}|{_HEBREW_NUMBERS}|{_ENGLISH_NUMBERS}){_AND_A_HALF}"
)
_SIZE = r"(?:\s*\([^()]{1,30}\))?"  # "1 (15 oz) can": a size between the amount and the unit
_MORE = rf"(?:\s*(?:\+|ועוד|plus)\s*(?:{_AMOUNT})\s*(?:{_UNIT})?)?"  # "1 כוס + 2 כפות"

# An amount where a word starts (or after one attached Hebrew letter), its unit if one follows.
_QUANTITY = re.compile(
    rf"(?:(?<!\w)|(?<=(?<!\w)[{_PREFIX}]))"
    rf"(?P<q>(?:{_WORD_AMOUNTS})(?!\w)|(?:{_AMOUNT})(?:{_SIZE}\s*(?:{_UNIT})(?![\w]))?{_MORE}"
    rf"|(?:{_AMOUNT})(?:{_UNIT})(?!\w))"
    rf"(?![\w/])",
    re.IGNORECASE,
)
# A unit with no number, at the start of the line, means one of it: "כוס חלב", "a pinch of salt".
_UNIT_FIRST = re.compile(rf"^(?:(?:a|an)\s+)?(?P<q>(?:{_UNIT}){_AND_A_HALF})(?!\w)", re.IGNORECASE)

# Rule 13: a measure or portion unit first and the line's number last ("גרם עוגיות טחונות 120", as text read
# from a screenshot can come out). Not a container: in "קופסת טונה 160" the number may be the can's size.
_CONTAINERS = re.compile(
    r"^(?:פחיות|פחית|קופסאות|קופסת|קופסה|חבילות|חבילת|חבילה|שקיות|שקית|שקיקים|שקיק|צנצנות|צנצנת|cans?|tins?|packages?|pkgs?\.?|packets?|jars?)$",
    re.IGNORECASE,
)
_BARE_NUMBER = re.compile(rf"(?<![\w/.,])(?:{_DIGITS})(?![\w/.,])")
_LAST_NUMBERS = re.compile(rf"((?:{_DIGITS}))((?:\s+\d+(?:[.,]\d+)?\s*%)*)[\s.,;:)\]]*$")  # "550", "550 5%"
_SIZE_BEFORE = re.compile(r"(?:קוטר|בקוטר|בגודל|גודל|באורך|ברוחב|x|×|על)\s*$", re.IGNORECASE)


def find_quantity(line: str) -> str | None:
    """The quantity span of an ingredient line, exactly as written in it, or None if it has none."""
    start = _UNIT_FIRST.match(line)
    if start:
        last = _last_number(line, start)
        if last is not None:
            return _span(line, *last)
        if _numbers_after_unit(line, start) > 1 and _LAST_NUMBERS.search(line[start.end():]):
            return None  # "גרם קמח 120 150": which number is the amount is not guessed (quantity_unclear)
        return _span(line, start.start(), start.end())
    for match in _QUANTITY.finditer(line):
        if _NOT_AN_AMOUNT.match(line, match.end("q")) and not re.search(rf"(?:{_UNIT})$", match["q"], re.IGNORECASE):
            continue  # "38%" or "2 ס״מ": a percentage or a size
        return _span(line, match.start("q"), match.end("q"))
    return None


def starts_with_amount(text: str) -> bool:
    """Does the text start with an amount ("2", "½", "חצי", "שתי")?"""
    return bool(re.match(rf"\s*(?:{_AMOUNT})(?![\w/])", text, re.IGNORECASE))


def starts_with_unit(text: str) -> bool:
    """Does the text start with a unit and no number before it ("גרם חמאה", "כוס מים")?"""
    return bool(_UNIT_FIRST.match(text.strip()))


def ends_with_unit(text: str) -> bool:
    return bool(re.search(rf"(?<!\w)(?:{_UNIT})\s*$", text, re.IGNORECASE))


def quantity_unclear(line: str) -> bool:
    """A line that starts with a unit and ends with numbers, none of them clearly the amount."""
    start = _UNIT_FIRST.match(line)
    return bool(start) and find_quantity(line) is None


def _last_number(line: str, start: re.Match) -> tuple[int, int] | None:
    """Rule 13: the span of the line's last number, when it is the line's only bare number after a
    measure or portion unit that starts the line; percentages after it are not amounts."""
    if _CONTAINERS.match(start["q"].split()[0]):
        return None
    rest_start = start.end()
    match = _LAST_NUMBERS.search(line, rest_start)
    if match is None or _numbers_after_unit(line, start) != 1:
        return None
    if _SIZE_BEFORE.search(line[rest_start:match.start(1)]) or _NOT_AN_AMOUNT.match(line, match.end(1)) and not match.group(2):
        return None
    return match.start(1), match.end(1)


def _numbers_after_unit(line: str, start: re.Match) -> int:
    """The bare numbers after the unit: not a percentage, a size, a temperature or a number with its own unit."""
    count = 0
    for number in _BARE_NUMBER.finditer(line, start.end()):
        after = line[number.end():]
        if _NOT_AN_AMOUNT.match(after) or re.match(rf"\s*(?:{_UNIT})(?!\w)", after, re.IGNORECASE):
            continue
        count += 1
    return count


def _span(line: str, start: int, end: int) -> str | None:
    text = line[start:end].rstrip(" ,;:")
    return text or None
