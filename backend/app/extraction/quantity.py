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


def find_quantity(line: str) -> str | None:
    """The quantity span of an ingredient line, exactly as written in it, or None if it has none."""
    start = _UNIT_FIRST.match(line)
    if start:
        return _span(line, start.start(), start.end())
    for match in _QUANTITY.finditer(line):
        if _NOT_AN_AMOUNT.match(line, match.end("q")) and not re.search(rf"(?:{_UNIT})$", match["q"], re.IGNORECASE):
            continue  # "38%" or "2 ס״מ": a percentage or a size
        return _span(line, match.start("q"), match.end("q"))
    return None


def _span(line: str, start: int, end: int) -> str | None:
    text = line[start:end].rstrip(" ,;:")
    return text or None
