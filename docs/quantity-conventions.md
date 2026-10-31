# Quantity conventions

An ingredient is stored as its **full line**, copied from the text, plus a separate **quantity**
field. These rules say what the quantity field holds. The evaluation's expectations
(`backend/evals/cases/*.json`) and the backend's quantity finder (`app/extraction/quantity.py`)
follow them, so the quantity can later be scaled by changing only that span of the line.

1. **A span of the line, exactly as written.** Same characters, same spelling, nothing added,
   converted or normalized. Never an amount the line does not write.
2. **The amount, and the unit that directly follows it.** "3 כוסות" in "3 כוסות קמח לבן",
   "200 גרם" in "200 גרם שוקולד", "230גרם" in "230גרם סוכר" (a unit attached to the number),
   "1/3 cup" in "1/3 cup feta".
3. **Never the ingredient itself.** A counted ingredient has no unit: "2" in "2 בצלים", "8" in
   "8 שוקיים עוף", "4" in "4 ביצים L".
4. **Amounts** are written as digits ("2"), decimals ("1.5", "1,5"), fractions ("1/2", "½"), mixed
   numbers ("1 1/2", "2 וחצי"), ranges ("2-3", "2–3", "3 עד 4"), number words ("אחד", "שתי",
   "שלוש", "one", "two"), fraction words ("חצי", "רבע", "שליש", "half"), and words that are an
   amount in themselves ("קצת", "מעט", "קורט", "חופן", "a pinch", "a handful", "a little").
5. **Units** are measures (כוס, כף, כפית, גרם / גר׳ / גר’, ק״ג, קילו, ליטר, מ״ל / מל׳, cup, tbsp,
   tsp, g, kg, ml, l, oz, lb) and portion or container words (קורט, חופן, צרור, שן / שיני, פרוסה,
   חתיכה, קוביה, ענף, פחית, קופסה, חבילה, שקית, צנצנת, שוט, can, clove, slice, piece, sprig,
   bunch, stick, jar, package). A modifier of the measure that follows it belongs to it ("2 כפות
   גדושות", "1 tsp heaped").
6. **A unit without a number means one of it:** "כוס" in "כוס חלב", "כף" in "כף פפריקה",
   "פחית" in "פחית חלב קוקוס", "קורט" in "קורט מלח". "כוס וחצי" is one quantity.
7. **An amount may come after the ingredient:** "אחד" in "בצל אחד גדול".
8. **Not part of the amount:** a prefix letter attached to it ("חצי" in "מיץ מחצי לימון"), an
   approximation ("200 גרם" in "כ-200 גרם"), a percentage or a size ("38%", "2 ס״מ").
9. **A size in parentheses between the amount and the unit belongs to it** ("1 (15 oz) can");
   one after the unit does not ("1 שקית" in "1 שקית שמרים (10 גרם)").
10. **Several amounts:** the first one, which measures the ingredient ("1" in "Juice of 1
    lemon"); amounts joined by "+" or "ועוד" are one quantity ("1 כוס + 2 כפות").
11. **No amount, no quantity (null):** "מלח ופלפל", "Salt and pepper, to taste", "שמן לטיגון",
    "קוקוס לגלגול", "אבקת סוכר (לא חובה)". Purposes ("לטיגון", "להגשה", "לקישוט", "to taste",
    "לפי הטעם") are not amounts.
12. **"a" or "an"** counts as an amount only before a unit or portion word ("a pinch", "a can");
    "an onion" has no quantity.
13. **A unit first and the amount last:** when a line starts with a measure or portion unit and its
    only number with no unit after it ends the line, that number is the amount: "120" in "גרם
    עוגיות טחונות 120", "550" in "גרם גבינה לבנה 550 5%" (text read from a screenshot can come
    out so). Only the number is the span: the line is never reordered. Not after a container
    ("קופסת" in "קופסת טונה 160": the number may be its size), not a size ("בקוטר 24"), not a
    number with its own unit ("כוס" in "כוס קמח (140 גרם)"). With two such numbers ("גרם קמח 120
    150") the amount is not guessed: no quantity, and the draft says which line to check.
