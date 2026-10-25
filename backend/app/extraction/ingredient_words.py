"""Words that name an ingredient, for noticing one that a recipe's steps use but its own ingredient
list leaves out ("מקשטים בתותים" with no strawberries in the list). Such a recipe is shown as written,
with a review point; nothing is added to its list and no amount is guessed.

A general list of common ingredients in Hebrew and English (singular, plural and usual spellings),
written for this purpose without looking at any recipe in the evaluation. Left out on purpose:
words with a common meaning outside the kitchen ("שום" is also "any", "מים" are rarely listed),
parts of an ingredient that a list names by the whole (egg whites and yolks, chicken thighs and
wings), and words of fewer than three letters (a prefix letter or two makes them out of other words).
"""

import re

HEBREW = frozenset({
    "אבוקדו", "אבטיח", "אבקת אפיה", "אבקת אפייה", "אבקת מרק", "אבקת סוכר", "אבקת שום", "אגוז מוסקט",
    "אגוז מלך", "אגוזי לוז", "אגוזי מלך", "אגס", "אגסים", "אדממה", "אווז", "אוכמניות", "אוכמנית",
    "אורגנו", "אורז", "אטריות", "איטריות", "אמנון", "אנטריקוט", "אניס", "אננס", "אנשובי", "אנשובים",
    "אסאדו", "אספרגוס", "אספרסו", "אפונה", "אפרסמון", "אפרסק", "אפרסקים", "ארוגולה", "ארטישוק",
    "ארטישוקים", "אשכוליות", "אשכולית", "באגט", "בהרט", "בוטן", "בוטנים", "בולגרית", "בורגול", "בורגל",
    "בורי", "בזיליקום", "בטטה", "בטטות", "בייקון", "ביסקוויט", "ביסקוויטים", "ביצה", "ביצים", "בירה",
    "בלסמי", "במיה", "בננה", "בננות", "בסמטי", "בצל", "בצל ירוק", "בצלים", "בצלצל", "בצלצלים",
    "בצק עלים", "בקלה", "בקר", "ברווז", "ברוקולי", "ברנדי", "בשר בקר", "בשר טחון", "ג'ינג'ר", "ג'לטין",
    "ג'לפניו", "גאודה", "גבינה לבנה", "גבינת ברי", "גבינת עיזים", "גבינת שמנת", "גויאבה", "גורגונזולה",
    "גזר", "גזרים", "גינגר", "גלטין", "גמבה", "גמבות", "גרוייר", "גריסים", "גרם מסאלה", "גרעיני דלעת",
    "גרעיני חמניה", "גרעיני חמנייה", "דבש", "דובדבן", "דובדבנים", "דיונון", "דיז'ון", "דלורית",
    "דלעות", "דלעת", "דניס", "דפנה", "הודו", "הלומי", "הריסה", "וודקה", "ווסטרשייר", "וניל", "זאתר",
    "זוקיני", "זית", "זיתים", "זנגביל", "זעפרן", "זעתר", "זרעי דלעת", "זרעי שומר", "חוואייג'",
    "חוויאג'", "חומוס", "חומץ", "חזה עוף", "חזיר", "חילבה", "חלב", "חלב מרוכז", "חלב קוקוס",
    "חלב שקדים", "חלבה", "חלה", "חלומי", "חלפיניו", "חמאה", "חמאת בוטנים", "חמוציות", "חמוצים", "חסה",
    "חסילונים", "חציל", "חצילים", "חרדל", "טונה", "טופו", "טורטיה", "טורטיות", "טחינה", "טילפיה",
    "טימין", "טלה", "טריאקי", "יוגורט", "יין", "כבד עוף", "כבדי עוף", "כוכב אניס", "כוסברה", "כוסמין",
    "כוסמת", "כורכום", "כמון", "כרוב", "כרוב ניצנים", "כרובית", "כרישה", "כרישות", "לאבנה", "לאפה",
    "לברק", "לוז", "לוקוס", "לזניה", "לחם", "לחמניה", "לחמניות", "לחמנייה", "ליים", "לימון", "לימונים",
    "לפה", "מולים", "מוסקט", "מוצרלה", "מיונז", "מייפל", "מיסו", "מלון", "מלח", "מלפפון", "מלפפונים",
    "מנגו", "מנגולד", "מנדרינה", "מנדרינות", "מנטה", "מסקרפונה", "מצה", "מצות", "מקרוני", "מרגרינה",
    "מרווה", "מרציפן", "מרשמלו", "נבטים", "נודלס", "נסיכת הנילוס", "נענע", "נקטרינה", "נקטרינות",
    "נקניק", "נקניקיה", "נקניקיות", "נקניקייה", "נקניקים", "סודה לשתיה", "סודה לשתייה", "סויה", "סוכר",
    "סולת", "סומק", "סחוג", "סטיביה", "סטייק", "סטייקים", "סילאן", "סילן", "סינטה", "סלמון", "סלמי",
    "סלק", "סלרי", "ספגטי", "סרדין", "סרדינים", "סרירצ'ה", "עגבניה", "עגבניות", "עגבנייה", "עגל",
    "עדשים", "עוף", "עירית", "עלה דפנה", "עלי דפנה", "עמבה", "עמילן", "ענבים", "ערמונים", "ערק",
    "פודינג", "פול", "פורל", "פטה", "פטל", "פטרוזיליה", "פטריה", "פטריות", "פטרייה", "פילו", "פיסטוק",
    "פיסטוקים", "פירורי לחם", "פירות יער", "פיתה", "פיתות", "פלפל", "פלפל אנגלי", "פלפל שחור",
    "פלפלים", "פנקו", "פסטה", "פסטרמה", "פפאיה", "פפריקה", "פקאן", "פקעת שומר", "פרג", "פרגיות",
    "פרגית", "פריקה", "פרמז'ן", "פרמזן", "פשתן", "פתי בר", "פתיתים", "צ'דר", "צ'יה", "צ'ילי", "צדפות",
    "צדר", "צילי", "צימוקים", "ציפורן", "צלפים", "צמוקים", "צנובר", "צנוברים", "צנון", "צנוניות",
    "צנונית", "צפורן", "צפתית", "קארי", "קוואקר", "קוטג", "קוטג'", "קולורבי", "קולרבי", "קוסקוס",
    "קוקוס", "קורנפלור", "קורנפלקס", "קטשופ", "קיווי", "קימל", "קינואה", "קינמון", "קישוא", "קישואים",
    "קלמארי", "קלמנטינה", "קלמנטינות", "קלמרי", "קמח", "קמח שקדים", "קממבר", "קנולה", "קנמון", "קפה",
    "קפיר", "קצח", "קקאו", "קרפיון", "קשיו", "קשקבל", "קשקוואל", "ראס אל חנות", "ראש שום", "רוזמרין",
    "רוטב דגים", "רוטב סויה", "רוטב צדפות", "רוקולה", "רוקט", "ריבה", "ריבת חלב", "ריחן", "רימון",
    "רימונים", "ריקוטה", "רסק עגבניות", "שאלוט", "שבולת שועל", "שומשום", "שוקולד", "שזיף", "שזיפים",
    "שיבולת שועל", "שיני שום", "שמיר", "שמן", "שמן זית", "שמן חמניות", "שמן צמחי", "שמן קוקוס",
    "שמן קנולה", "שמן שומשום", "שמנת", "שמנת חמוצה", "שמנת מתוקה", "שמפיניון", "שמפיניונים", "שמרים",
    "שן שום", "שעועית", "שפונדרה", "שקד", "שקדים", "שרימפס", "תאנה", "תאנים", "תות", "תותי שדה",
    "תותים", "תימין", "תירס", "תמנון", "תמר", "תמרים", "תפוז", "תפוזים", "תפוח אדמה", "תפוח עץ",
    "תפוחי אדמה", "תפוחי עץ", "תפוחים", "תרד",
})

ENGLISH = frozenset({
    "agave", "allspice", "almond", "almond flour", "almond milk", "almonds", "amba", "anchovies",
    "anchovy", "anise", "apple", "apples", "apricot", "apricots", "arak", "artichoke", "artichokes",
    "arugula", "asparagus", "aubergine", "aubergines", "avocado", "avocados", "bacon", "baguette",
    "baharat", "baking powder", "baking soda", "balsamic", "banana", "bananas", "barley", "basil",
    "basmati", "bay leaf", "bay leaves", "beef", "beer", "beet", "beetroot", "beets", "bell pepper",
    "bell peppers", "bicarbonate of soda", "biscuits", "black beans", "black pepper", "blackberries",
    "blackberry", "blue cheese", "blueberries", "blueberry", "bouillon", "brandy", "bread",
    "bread crumbs", "breadcrumbs", "brie", "brisket", "broccoli", "broth", "brussels sprouts",
    "buckwheat", "bulgur", "butter", "buttermilk", "butternut", "cabbage", "calamari", "camembert",
    "canola oil", "capers", "caraway", "cardamom", "carp", "carrot", "carrots", "cashew", "cashews",
    "cauliflower", "cayenne", "celery", "challah", "chard", "cheddar", "cherries", "cherry",
    "chestnut", "chestnuts", "chia", "chicken", "chickpea", "chickpeas", "chile", "chiles", "chili",
    "chilies", "chilli", "chillies", "chives", "chocolate", "cilantro", "cinnamon", "clam", "clams",
    "clementine", "clementines", "cocoa", "coconut", "coconut milk", "coconut oil", "cod", "coffee",
    "condensed milk", "coriander", "corn", "cornflakes", "cornflour", "cornstarch", "cottage cheese",
    "courgette", "courgettes", "couscous", "crab", "cranberries", "cranberry", "cream cheese",
    "cucumber", "cucumbers", "cumin", "curry powder", "date syrup", "dates", "dijon", "dill",
    "double cream", "duck", "dulce de leche", "edamame", "egg", "eggplant", "eggplants", "eggs",
    "espresso", "fava beans", "fennel", "fenugreek", "feta", "fig", "figs", "filo", "fish sauce",
    "flaxseed", "flaxseeds", "flour", "freekeh", "garam masala", "garlic", "gelatin", "gelatine",
    "ghee", "ginger", "goat cheese", "goose", "gorgonzola", "gouda", "grape", "grapefruit", "grapes",
    "green beans", "green onion", "green onions", "ground cloves", "gruyere", "halloumi", "halva",
    "halvah", "ham", "harissa", "hawaij", "hazelnut", "hazelnuts", "heavy cream", "honey", "hummus",
    "icing sugar", "jalapeno", "jalapenos", "jalapeño", "jalapeños", "jam", "kale", "kefir", "ketchup",
    "kidney beans", "kiwi", "kohlrabi", "labneh", "lamb", "lasagna", "lasagne", "leek", "leeks",
    "lemon", "lemons", "lentil", "lentils", "lettuce", "lime", "limes", "liver", "livers", "lobster",
    "macaroni", "mandarin", "mandarins", "mango", "mangoes", "maple syrup", "margarine",
    "marshmallows", "marzipan", "mascarpone", "matzah", "matzo", "mayo", "mayonnaise", "melon", "milk",
    "mint", "miso", "mozzarella", "mushroom", "mushrooms", "mussel", "mussels", "mustard", "nectarine",
    "nectarines", "nigella", "noodles", "nutmeg", "oatmeal", "oats", "octopus", "oil", "okra", "olive",
    "olive oil", "olives", "onion", "onions", "orange", "oranges", "oregano", "oyster", "oyster sauce",
    "oysters", "panko", "papaya", "paprika", "parmesan", "parsley", "parsnip", "parsnips", "pasta",
    "pastrami", "peach", "peaches", "peanut", "peanut butter", "peanuts", "pear", "pears", "peas",
    "pecan", "pecans", "penne", "pepper", "peppercorns", "peppers", "persimmon", "phyllo", "pickles",
    "pine nuts", "pineapple", "pistachio", "pistachios", "pita", "plum", "plums", "pomegranate",
    "pomegranates", "poppy seeds", "pork", "potato", "potato starch", "potatoes", "powdered sugar",
    "prawn", "prawns", "prune", "prunes", "puff pastry", "pumpkin", "pumpkin seeds", "quinoa",
    "radish", "radishes", "raisin", "raisins", "ras el hanout", "raspberries", "raspberry",
    "red pepper flakes", "rice", "ricotta", "rosemary", "rum", "saffron", "sage", "salami", "salmon",
    "salt", "sardine", "sardines", "sausage", "sausages", "scallion", "scallions", "scallop",
    "scallops", "schug", "sea bass", "sea bream", "semolina", "sesame", "sesame oil", "shallot",
    "shallots", "sherry", "shrimp", "silan", "sour cream", "soy sauce", "soybeans", "spaghetti",
    "spelt", "spinach", "spring onion", "spring onions", "sprouts", "squash", "squid", "sriracha",
    "star anise", "steak", "steaks", "stevia", "strawberries", "strawberry", "sugar", "sumac",
    "sunflower oil", "sunflower seeds", "sweet potato", "sweet potatoes", "tahini", "tangerine",
    "tangerines", "tea", "tenderloin", "teriyaki", "thyme", "tilapia", "tofu", "tomato",
    "tomato paste", "tomato puree", "tomatoes", "tortilla", "tortillas", "trout", "tuna", "turkey",
    "turmeric", "turnip", "turnips", "vanilla", "veal", "vegetable oil", "vinegar", "vodka", "walnut",
    "walnuts", "watermelon", "whipping cream", "white beans", "wine", "worcestershire", "yeast",
    "yoghurt", "yogurt", "za'atar", "zaatar", "zhug", "zucchini",
})

# Two names for the same ingredient, so that one in the list covers the other in the steps.
SAME_INGREDIENT = [
    {"גינגר", "זנגביל"}, {"צימוקים", "צמוקים"}, {"אטריות", "איטריות"}, {"קשקבל", "קשקוואל"},
    {"בורגול", "בורגל"}, {"סילאן", "סילן"}, {"קינמון", "קנמון"}, {"זאתר", "זעתר"}, {"ציפורן", "צפורן"},
    {"חלומי", "הלומי"}, {"קולורבי", "קולרבי"}, {"קלמרי", "קלמארי"}, {"ארוגולה", "רוקולה", "רוקט"},
    {"חלפיניו", "ג'לפניו"}, {"שיבולת שועל", "שבולת שועל", "קוואקר"}, {"ריחן", "בזיליקום"},
    {"בצל ירוק", "בצלצל"}, {"קורנפלור", "עמילן"}, {"חוואייג'", "חוויאג'"}, {"נענע", "מנטה"},
    {"cilantro", "coriander"}, {"courgette", "zucchini"}, {"aubergine", "eggplant"},
    {"scallion", "green onion", "spring onion"}, {"icing sugar", "powdered sugar"}, {"cornflour", "cornstarch"},
    {"chile", "chili", "chilli"}, {"yoghurt", "yogurt"}, {"matzah", "matzo"}, {"phyllo", "filo"},
    {"prawn", "shrimp"}, {"double cream", "heavy cream", "whipping cream"}, {"bicarbonate of soda", "baking soda"},
    {"beet", "beetroot"}, {"zhug", "schug"}, {"halva", "halvah"}, {"whisky", "whiskey"}, {"mayo", "mayonnaise"},
    {"gelatin", "gelatine"}, {"jalapeno", "jalapeño"}, {"lasagna", "lasagne"}, {"gruyere", "gruyère"},
]

_PREFIXES = "ומבלכשה"
_WORD = re.compile(r"\w+(?:['׳’]\w+)*'?")
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")
# A clause that serves the dish with something else ("מגישים עם אורז לבן", "Serve with pita"): an
# accompaniment, a dish of its own, not an ingredient the list left out.
_ACCOMPANIMENT = re.compile(
    r"(?:מגישים|להגיש|הגישו|מוגש|מוגשת|ומגישים)\s+(?:עם|לצד|על)\s"
    r"|\bserve[ds]?\s+(?:\w+\s+){0,3}(?:with|alongside|over|on)\b",
    re.IGNORECASE,
)
_CLAUSE = re.compile(r"[^.,;!?]+")


def _key(word: str) -> str:
    """One spelling for comparing: no apostrophes ("ג'ינג'ר" = "גינגר"), one yod or vav where some
    write two ("אפייה" = "אפיה"), no final letter forms, lower case."""
    word = re.sub(r"['׳’״\"]", "", word.lower()).translate(_FINALS)
    return word.replace("יי", "י").replace("וו", "ו")


def _stem(key: str) -> str:
    """Singular and plural alike: "תותים" and "תות", "ביצה" and "ביצים", "tomatoes" and "tomato"."""
    if re.search("[א-ת]", key):
        for ending in ("ימ", "ות", "ה"):  # "ים" after the final letters were made regular
            if key.endswith(ending) and len(key) - len(ending) >= 2:
                return key[: -len(ending)]
        return key
    if key.endswith("ies"):
        return key[:-3] + "y"
    if key.endswith(("oes", "ches", "shes", "xes", "sses")):
        return key[:-2]
    return key[:-1] if key.endswith("s") and not key.endswith("ss") and len(key) > 3 else key


def _listed_stems(word: str) -> set[str]:
    """How a word in an ingredient line can name an ingredient: its stem, and for a Hebrew plural
    before another noun the plural itself ("נבטי חמניות", "פתיתי מלח": "נבטים", "פתיתים")."""
    key = _key(word)
    stems = {_stem(key)}
    if re.search("[א-ת]", key) and key.endswith("י") and len(key) > 3:
        stems.add(key[:-1])
    return stems


def _forms(word: str) -> list[str]:
    """The word, and the word without one or two Hebrew prefix letters ("ובתותים" -> "בתותים", "תותים")."""
    forms = [word]
    for _ in range(2):
        last = forms[-1]
        if last[:1] in _PREFIXES and len(last) > 3:
            forms.append(last[1:])
    return forms


_SINGLE = {_key(w): w for w in HEBREW | ENGLISH if " " not in w}
_SEVERAL = {tuple(_key(p) for p in w.split()): w for w in HEBREW | ENGLISH if " " in w}
_LONGEST = max(len(k) for k in _SEVERAL)
_SAME = {_key(w): group for group in SAME_INGREDIENT for w in group}


def _listed(entry: str, listed: set[str]) -> bool:
    """Does the ingredient list have this ingredient (every word of it, or of another name for it)?"""
    for name in _SAME.get(_key(entry), {entry}):
        if all(_stem(_key(word)) in listed for word in name.split()):
            return True
    return False


def only_in_steps(lines: list[str], steps: list[str]) -> list[tuple[str, str]]:
    """Each ingredient word that a step uses and no ingredient line has: (the words as the step writes
    them, without a prefix letter, and the step). The first step that uses it; longer names first
    ("שמן זית" rather than "שמן" and "זית"); not what the dish is served with."""
    listed = {stem for line in lines for word in _WORD.findall(line) for form in _forms(word) for stem in _listed_stems(form)}
    found: dict[str, tuple[str, str]] = {}
    clauses = [(clause, step) for step in steps for clause in _CLAUSE.findall(step) if not _ACCOMPANIMENT.search(clause)]
    for clause, step in clauses:
        words = _WORD.findall(clause)
        i = 0
        while i < len(words):
            match = None
            for form in _forms(words[i]):
                for n in range(_LONGEST, 1, -1):
                    entry = _SEVERAL.get((_key(form), *(_key(w) for w in words[i + 1 : i + n])))
                    if entry and i + n <= len(words):
                        match = (entry, " ".join([form, *words[i + 1 : i + n]]), n)
                        break
                if match is None and _key(form) in _SINGLE:
                    match = (_SINGLE[_key(form)], form, 1)
                if match:
                    break
            if match is None:
                i += 1
                continue
            entry, written, n = match
            i += n
            group = min(_SAME.get(_key(entry), {entry}))  # one review point for two names of one ingredient
            if group not in found and not _listed(entry, listed):
                found[group] = (written, step)
    return list(found.values())
