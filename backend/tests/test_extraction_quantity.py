"""Finding an ingredient line's quantity: docs/quantity-conventions.md, rule by rule."""

import pytest

from app.extraction.quantity import find_quantity


@pytest.mark.parametrize(
    ("line", "quantity"),
    [
        # 2. The amount and the unit that follows it, also attached to the number.
        ("3 כוסות קמח לבן", "3 כוסות"),
        ("500 גרם בשר טחון", "500 גרם"),
        ("250גר׳ חמאה", "250גר׳"),
        ("150מ״ל חלב", "150מ״ל"),
        ("1/3 cup feta", "1/3 cup"),
        ("2 tablespoons honey", "2 tablespoons"),
        ("100g dark chocolate", "100g"),
        # 3. Never the ingredient itself.
        ("2 בצלים", "2"),
        ("6 כרעיים עוף", "6"),
        ("4 ביצים L בטמפרטורת החדר", "4"),
        ("3 eggs", "3"),
        # 4. Fractions, mixed numbers, decimals, ranges, words.
        ("½ כוס סוכר", "½ כוס"),
        ("1 1/2 כוסות מים", "1 1/2 כוסות"),
        ("1.5 ליטר ציר", "1.5 ליטר"),
        ("2 וחצי כוסות אורז", "2 וחצי כוסות"),
        ("2-3 שיני שום", "2-3 שיני"),
        ("2–3 tbsp olive oil", "2–3 tbsp"),
        ("3 עד 4 תפוחים", "3 עד 4"),
        ("שתי כוסות קמח", "שתי כוסות"),
        ("שלוש ביצים", "שלוש"),
        ("רבע כוס שמן", "רבע כוס"),
        ("שלושת רבעי כוס סוכר", "שלושת רבעי כוס"),
        ("two cups flour", "two cups"),
        ("קצת שמן זית", "קצת"),
        ("מעט מלח", "מעט"),
        ("a pinch of salt", "a pinch"),
        ("A handful of basil", "A handful"),
        # 5. Units and portion words, with a modifier of the measure.
        ("4 שיני שום", "4 שיני"),
        ("2 פרוסות לחם", "2 פרוסות"),
        ("1 צרור פטרוזיליה", "1 צרור"),
        ("2 כפות גדושות קקאו", "2 כפות גדושות"),
        ("1 tsp heaped cinnamon", "1 tsp heaped"),
        ("3 cloves garlic", "3 cloves"),
        # 6. A unit without a number means one of it.
        ("כוס חלב", "כוס"),
        ("כף סילאן", "כף"),
        ("פחית תירס (340 גרם)", "פחית"),
        ("קורט קינמון", "קורט"),
        ("כוס וחצי קמח", "כוס וחצי"),
        ("חתיכת ג׳ינג׳ר (3 ס״מ)", "חתיכת"),
        # 7. An amount after the ingredient.
        ("בצל אחד גדול", "אחד"),
        ("פלפל אדום אחד", "אחד"),
        ("ביצה אחת", "אחת"),
        # 8. Not part of the amount: an attached prefix, an approximation, a percentage, a size.
        ("מיץ מחצי לימון", "חצי"),
        ("כ-300 גרם עוף", "300 גרם"),
        ("שמנת מתוקה 32%", None),
        ("200 גרם שוקולד 70%", "200 גרם"),
        # 9. A size in parentheses between the amount and the unit belongs to it.
        ("1 (400 g) can tomatoes", "1 (400 g) can"),
        ("1 שקית אבקת אפייה (10 גרם)", "1 שקית"),
        # 10. The first amount; amounts joined by "+" or "ועוד" are one quantity.
        ("Juice of 2 limes", "2"),
        ("1 כוס + 2 כפות סוכר", "1 כוס + 2 כפות"),
        ("חצי כוס ועוד 2 כפות שמן", "חצי כוס ועוד 2 כפות"),
        # 11. No amount, no quantity.
        ("מלח ופלפל", None),
        ("Salt and pepper, to taste", None),
        ("שמן לטיגון", None),
        ("אבקת סוכר (לא חובה)", None),
        ("עלי בזיליקום להגשה", None),
        ("לקישוט - שומשום", None),
        # 12. "a" or "an" only before a unit.
        ("an onion, chopped", None),
        ("a can of beans", "a can"),
    ],
)
def test_the_quantity_follows_the_conventions(line: str, quantity: str | None):
    assert find_quantity(line) == quantity


def test_the_quantity_is_always_a_span_of_the_line():
    for line in ["3 כוסות קמח", "בצל אחד גדול", "מיץ מחצי לימון", "1 (400 g) can tomatoes", "כוס וחצי קמח"]:
        quantity = find_quantity(line)
        assert quantity is not None and quantity in line


def test_words_that_only_contain_an_amount_are_not_amounts():
    assert find_quantity("כוסברה קצוצה") is None  # not "כוס"
    assert find_quantity("שמנת לבישול") is None
    assert find_quantity("תפוחי עץ לקישוט") is None
