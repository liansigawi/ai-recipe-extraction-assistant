"""Extraction by reference: numbered passages labeled by the model, drafts copied from the original.

The model's answers are written by hand here; these tests never call a model.
"""

import json

import httpx2

from app.extraction.ollama import OllamaExtractor
from app.extraction.output import ReferenceOutput, reference_schema
from app.extraction.prompt import CLASSIFY_SYSTEM_PROMPT, REFERENCE_SYSTEM_PROMPT, build_request
from app.extraction.review import build_draft_from_references, is_recipe, make_draft
from app.extraction.segments import passage_key, passage_text, render_segments, segment_text
from app.schemas import Category

CATEGORIES = [Category(id=1, name="קינוחים"), Category(id=2, name="בישולים"), Category(id=3, name="ארוחות קלילות")]

# The kind of caption that showed the problem: an introduction, then the recipe. The words that a
# small model retyped wrongly ("מג׳הול", "שוט") are here; with references they are never retyped.
DRINK = """לכבוד היום האחרון של הקיץ הכנתי משקה - חד משמעית כן! זו הכלאה בין שייק בננה ואייס קפה.

הגירסה שלי:
חצי תמר מג׳הול
שוט אספרסו
כוס חלב ש״ש
2-3 קוביות קרח

לערבל הכל יחד עד קבלת משקה ולרוויה!"""


def texts(source: str) -> list[str]:
    segments = segment_text(source)
    return [passage_text(source, segments, s.id, s.id) for s in segments]


# --- Passages -------------------------------------------------------------------------------------


def test_lines_are_passages_and_long_lines_are_cut_at_sentence_ends_and_labels():
    assert texts(DRINK) == [
        "לכבוד היום האחרון של הקיץ הכנתי משקה - חד משמעית כן!",
        "זו הכלאה בין שייק בננה ואייס קפה.",
        "הגירסה שלי",  # the heading's ":" is list punctuation, not wording
        "חצי תמר מג׳הול",
        "שוט אספרסו",
        "כוס חלב ש״ש",
        "2-3 קוביות קרח",
        "לערבל הכל יחד עד קבלת משקה ולרוויה!",
    ]


def test_a_list_after_a_label_is_cut_into_items_other_commas_and_dashes_are_not():
    assert texts("מצרכים: 2 כרישות, צרור תרד, 4 ביצים.") == ["מצרכים", "2 כרישות", "צרור תרד", "4 ביצים."]
    assert texts("1 (15 oz) can chickpeas, drained and rinsed") == ["1 (15 oz) can chickpeas, drained and rinsed"]
    assert texts("אופים 25 דקות ב-170 מעלות - המרכז צריך להישאר לח.") == ["אופים 25 דקות ב-170 מעלות - המרכז צריך להישאר לח."]
    assert texts("ארוחת בוקר של שישי: שקשוקה ירוקה 💚") == ["ארוחת בוקר של שישי", "שקשוקה ירוקה 💚"]


def test_a_piece_without_letters_joins_the_next_passage():
    assert texts("1. מערבבים הכול. 2. אופים.") == ["1. מערבבים הכול.", "2. אופים."]


def test_a_line_of_only_digits_is_kept_and_a_line_of_only_symbols_is_not_a_passage():
    assert texts("12\n👇📌\nמערבבים.") == ["12", "מערבבים."]


def test_passages_are_copied_character_for_character_and_a_line_break_becomes_a_space():
    source = "קוצצים בצל ומטגנים עד להזהבה, \nמוסיפים גזר חתוך, מטגנים כ2 דקות,\nמוסיפים את הפתיתים."
    segments = segment_text(source)
    assert passage_text(source, segments, 1, 3) == "קוצצים בצל ומטגנים עד להזהבה, מוסיפים גזר חתוך, מטגנים כ2 דקות, מוסיפים את הפתיתים."
    assert passage_text(source, segments, 1, 1) == "קוצצים בצל ומטגנים עד להזהבה"  # the list comma at the end is not wording


def test_the_same_text_always_gives_the_same_passages():
    assert segment_text(DRINK) == segment_text(DRINK)


def test_the_model_sees_each_line_as_written_with_numbers_before_its_passages():
    rendered = render_segments(DRINK, segment_text(DRINK))
    assert "[1] לכבוד היום האחרון של הקיץ הכנתי משקה - חד משמעית כן! [2] זו הכלאה" in rendered
    assert "\n\n[3] הגירסה שלי:\n[4] חצי תמר מג׳הול\n" in rendered


def test_a_passage_is_named_by_its_number_and_opening_words():
    segments = segment_text(DRINK)
    assert passage_key(DRINK, segments[4]) == "[5] שוט אספרסו"
    assert passage_key(DRINK, segments[0]) == "[1] לכבוד היום האחרון של הקיץ הכנתי משקה - חד משמעית כ…"


def test_the_request_gives_numbered_passages_and_the_answer_must_label_each_in_order():
    request = build_request(DRINK, CATEGORIES, "references")
    assert request.system == REFERENCE_SYSTEM_PROMPT and len(request.segments) == 8
    assert "[5] שוט אספרסו" in request.user
    keys = [passage_key(DRINK, segment) for segment in request.segments]
    passages = request.schema["properties"]["passages"]
    assert list(passages["properties"]) == keys and passages["required"] == keys
    assert passages["additionalProperties"] is False
    assert passages["properties"]["[4] חצי תמר מג׳הול"] == {"$ref": "#/$defs/PassageRole"}  # a role, nothing written
    assert "ingredient" in request.schema["$defs"]["PassageRole"]["enum"]
    assert request.schema == reference_schema(CATEGORIES, keys)


# --- Drafts from labels --------------------------------------------------------------------------

DRINK_ROLES = ["not_recipe", "not_recipe", "ingredient_heading", "ingredient", "ingredient", "ingredient", "ingredient", "step"]


def labels(source: str, roles: list[str]) -> dict:
    segments = segment_text(source)
    assert len(roles) == len(segments)
    return {passage_key(source, segment): role for segment, role in zip(segments, roles)}


def answer(source: str = DRINK, roles: list[str] | None = None, **changes) -> ReferenceOutput:
    """A correct answer for DRINK, unless a test gives another text and its roles."""
    roles = DRINK_ROLES if roles is None else roles
    data = {
        "is_recipe": True,
        "title": "שייק בננה ואייס קפה",
        "title_written_in_text": False,
        "servings": None,
        "passages": labels(source, roles),
        "only_in_steps": [],
        "issues": [],
        "dish": "a cold drink",
        "classification": {"fit": "no_fit", "category_id": None, "subcategory_id": None, "candidate_category_ids": []},
    }
    data.update(changes)
    return ReferenceOutput.model_validate(data)


def draft_of(output: ReferenceOutput, source: str = DRINK):
    return build_draft_from_references(output, source, segment_text(source), CATEGORIES)


def draft_for(source: str, roles: list[str], **changes):
    return draft_of(answer(source, roles, **changes), source)


def kinds(draft) -> list[str]:
    return [issue.kind for issue in draft.issues]


def ingredient_texts(draft) -> list[str]:
    return [i.text for g in draft.ingredient_groups for i in g.ingredients]


def test_the_recipe_is_copied_from_the_original_exactly():
    draft = draft_of(answer())
    assert ingredient_texts(draft) == ["חצי תמר מג׳הול", "שוט אספרסו", "כוס חלב ש״ש", "2-3 קוביות קרח"]
    assert [i.quantity for i in draft.ingredient_groups[0].ingredients] == ["חצי", "שוט", "כוס", "2-3 קוביות"]
    assert draft.ingredient_groups[0].name == "הגירסה שלי"
    assert draft.step_groups[0].steps == ["לערבל הכל יחד עד קבלת משקה ולרוויה!"]
    # The introduction is not in the recipe; the composed title and the missing category are explained.
    assert kinds(draft) == ["classification_unresolved", "missing_title"]


def test_a_passage_without_a_label_is_quoted_in_a_review_point_never_dropped_silently():
    output = answer()
    del output.passages["[7] 2-3 קוביות קרח"]
    draft = draft_of(output)
    assert ingredient_texts(draft) == ["חצי תמר מג׳הול", "שוט אספרסו", "כוס חלב ש״ש"]
    [unused] = [issue for issue in draft.issues if issue.kind == "unused_text"]
    assert unused.quote == "2-3 קוביות קרח"


def test_neighbouring_passages_without_labels_are_reported_together():
    output = answer()
    for key in list(output.passages)[:2]:
        del output.passages[key]
    unused = [issue for issue in draft_of(output).issues if issue.kind == "unused_text"]
    assert len(unused) == 1 and unused[0].quote.startswith("לכבוד היום האחרון")


def test_continues_adds_the_passage_to_the_item_before_it():
    draft = draft_for("פורסים את הכרישות ומטגנים בשמן זית\nעד שהן רכות, כ-10 דקות.", ["step", "continues"])
    assert draft.step_groups[0].steps == ["פורסים את הכרישות ומטגנים בשמן זית עד שהן רכות, כ-10 דקות."]


def test_continues_after_an_introduction_stays_out_of_the_recipe():
    draft = draft_for("סיפור ארוך על סבתא.\nועוד קצת סיפור.\nמערבבים הכול.", ["not_recipe", "continues", "step"])
    assert draft.step_groups[0].steps == ["מערבבים הכול."]
    assert not {"unused_text", "invalid_reference"} & set(kinds(draft))


def test_continues_with_nothing_before_it_is_reported_not_guessed():
    draft = draft_for("2 כוסות קמח\nמערבבים הכול.", ["continues", "step"])
    assert draft.ingredient_groups == [] and draft.step_groups[0].steps == ["מערבבים הכול."]
    [point] = [issue for issue in draft.issues if issue.kind == "invalid_reference"]
    assert point.quote == "2 כוסות קמח"


def test_each_quantity_is_read_from_its_copied_line_wherever_the_amount_is():
    source = "בצל אחד גדול\nמיץ מחצי לימון\nמלח ופלפל\nמערבבים."
    draft = draft_for(source, ["ingredient", "ingredient", "ingredient", "step"])
    assert [(i.text, i.quantity) for i in draft.ingredient_groups[0].ingredients] == [
        ("בצל אחד גדול", "אחד"), ("מיץ מחצי לימון", "חצי"), ("מלח ופלפל", None)]


def test_a_label_is_a_heading_whatever_role_the_answer_gives_it():
    roles = ["not_recipe", "not_recipe", "ingredient", "ingredient", "ingredient", "ingredient", "ingredient", "step"]
    draft = draft_of(answer(roles=roles))
    assert ingredient_texts(draft) == ["חצי תמר מג׳הול", "שוט אספרסו", "כוס חלב ש״ש", "2-3 קוביות קרח"]
    assert draft.ingredient_groups[0].name == "הגירסה שלי"
    draft = draft_for("איך מכינים: משרים את העדשים שעה במים.", ["step", "continues"])
    assert draft.step_groups[0].steps == ["משרים את העדשים שעה במים."]


def test_a_tip_keeps_its_words_without_its_label():
    for roles in (["step", "tip", "continues"], ["step", "tip", "tip"]):
        draft = draft_for("מערבבים הכול.\nטיפ: אפשר להקפיא עד חודש.", roles)
        assert draft.notes == ["אפשר להקפיא עד חודש."]


def test_hashtags_and_mentions_are_never_recipe_content():
    draft = draft_for("מערבבים הכול.\nאפשר להקפיא.\n#עוגה #אפייה @baker 👇", ["step", "tip", "tip"])
    assert draft.notes == ["אפשר להקפיא."]
    assert "unused_text" not in kinds(draft)


def test_ingredient_and_step_groups_follow_the_texts_headings():
    source = "לבצק:\n2 כוסות קמח\nלמילוי:\nריבה\nבסיר לחץ:\nמבשלים 40 דקות.\nבסיר רגיל:\nמבשלים כשלוש שעות."
    roles = ["ingredient_heading", "ingredient", "ingredient_heading", "ingredient", "step_heading", "step", "step_heading", "step"]
    draft = draft_for(source, roles)
    assert [(g.name, [i.text for i in g.ingredients]) for g in draft.ingredient_groups] == [("לבצק", ["2 כוסות קמח"]), ("למילוי", ["ריבה"])]
    assert [(g.name, g.steps) for g in draft.step_groups] == [("בסיר לחץ", ["מבשלים 40 דקות."]), ("בסיר רגיל", ["מבשלים כשלוש שעות."])]


def test_step_numbers_are_left_out_even_as_keycap_emoji():
    draft = draft_for("1️⃣ מחממים תנור ל-170 מעלות.\n2. אופים 12 דקות.", ["step", "step"])
    assert draft.step_groups[0].steps == ["מחממים תנור ל-170 מעלות.", "אופים 12 דקות."]


def test_the_title_line_loses_its_emoji():
    source = "מרק עדשים כתומות 🌶️\nמבשלים 20 דקות."
    draft = draft_for(source, ["title", "step"], title="מרק עדשים כתומות 🌶️", title_written_in_text=True)
    assert draft.title == "מרק עדשים כתומות"
    assert "unused_text" not in kinds(draft)


def test_a_title_the_model_misspelled_is_taken_from_the_passage_it_labeled_as_the_title():
    source = "מרק עדשים כתומות 🌶️\nמבשלים 20 דקות."
    draft = draft_for(source, ["title", "step"], title="מרк עדשים כתומות", title_written_in_text=True)
    assert draft.title == "מרק עדשים כתומות"
    assert "not_found_in_source" not in kinds(draft)


def test_a_misspelled_title_without_a_labeled_title_line_is_kept_and_flagged():
    source = "מרק עדשים כתומות\nמבשלים 20 דקות."
    draft = draft_for(source, ["not_recipe", "step"], title="מרк עדשים כתומות", title_written_in_text=True)
    assert draft.title == "מרк עדשים כתומות"
    assert "not_found_in_source" in kinds(draft)


def test_a_title_the_model_found_in_the_text_is_kept_even_if_the_line_says_more():
    source = "טארט דבש מלוח, בדיוק כמו במסעדה\n200 גרם דבש\nאופים."
    draft = draft_for(source, ["title", "ingredient", "step"], title="טארט דבש מלוח", title_written_in_text=True)
    assert draft.title == "טארט דבש מלוח"
    assert ingredient_texts(draft) == ["200 גרם דבש"]


def test_the_title_line_labeled_as_an_ingredient_stays_the_title_only():
    source = "כדורי תמרים ושקדים\n1 כוס תמרים\nמגלגלים כדורים."
    draft = draft_for(
        source, ["ingredient", "ingredient", "step"], title="כדורי תמרים ושקדים", title_written_in_text=True
    )
    assert ingredient_texts(draft) == ["1 כוס תמרים"]


def test_a_line_that_only_contains_the_title_words_is_still_an_ingredient():
    source = "חומוס\n1 כוס חומוס מבושל\nטוחנים."
    draft = draft_for(source, ["title", "ingredient", "step"], title="חומוס", title_written_in_text=True)
    assert ingredient_texts(draft) == ["1 כוס חומוס מבושל"]


def test_a_prose_list_gives_one_ingredient_per_item_without_the_final_period():
    source = "מצרכים: 2 כרישות, צרור תרד, 4 ביצים.\nמטגנים הכול."
    draft = draft_for(source, ["ingredient_heading", "ingredient", "ingredient", "ingredient", "step"])
    assert ingredient_texts(draft) == ["2 כרישות", "צרור תרד", "4 ביצים"]
    assert draft.ingredient_groups[0].name is None  # "מצרכים" only names the list


def test_a_review_point_has_a_fixed_message_and_quotes_its_passage_from_the_original():
    draft = draft_of(answer(issues=[{"kind": "unclear_text", "passage": 7}]))
    [point] = [issue for issue in draft.issues if issue.kind == "unclear_text"]
    assert point.quote == "2-3 קוביות קרח"
    assert point.message == "הקטע הזה נראה חתוך, משובש או לא ברור. השוו למקור."


def test_a_point_without_its_passage_or_about_text_left_out_of_the_recipe_is_not_shown():
    points = [
        {"kind": "unclear_text", "passage": None},  # no evidence
        {"kind": "unclear_text", "passage": 1},  # the introduction: labeled not part of the recipe
        {"kind": "ambiguous_alternative", "passage": 5},  # an ingredient: shown, quoting it
        {"kind": "multiple_recipes", "passage": None},  # about the whole text
    ]
    shown = [(issue.kind, issue.quote) for issue in draft_of(answer(issues=points)).issues]
    assert ("ambiguous_alternative", "שוט אספרסו") in shown and ("multiple_recipes", None) in shown
    assert "unclear_text" not in [kind for kind, _ in shown]


MUFFINS = "מאפינס\n2 כוסות קמח\nמוסיפים את הקמח ואת התותים החתוכים.\nאופים 20 דקות ב-180 מעלות."
MUFFIN_ROLES = ["title", "ingredient", "step", "step"]


def test_an_ingredient_only_in_the_steps_is_shown_only_with_its_evidence():
    claims = [
        {"passage": 3, "words": "התותים"},  # in that step, and in no ingredient line: shown
        {"passage": 3, "words": "הקמח"},  # in the ingredient list ("2 כוסות קמח")
        {"passage": 3, "words": "האוכמניות"},  # not what that step writes
        {"passage": 2, "words": "קמח"},  # not a step
        {"passage": 3, "words": "מים"},  # water is rarely listed
    ]
    draft = draft_for(MUFFINS, MUFFIN_ROLES, title="מאפינס", title_written_in_text=True, only_in_steps=claims)
    [point] = [issue for issue in draft.issues if issue.kind == "ingredient_only_in_steps"]
    assert '"התותים"' in point.message and point.quote == "מוסיפים את הקמח ואת התותים החתוכים."


def test_missing_oven_temperature_and_baking_time_come_from_the_text_itself():
    complete = draft_for(MUFFINS, MUFFIN_ROLES, title="מאפינס", title_written_in_text=True)
    assert "missing_information" not in kinds(complete)
    source = "פשטידה\n3 ביצים\nיוצקים לתבנית ואופים עד שהפשטידה זהובה."
    draft = draft_for(source, ["title", "ingredient", "step"], title="פשטידה", title_written_in_text=True)
    messages = [issue.message for issue in draft.issues if issue.kind == "missing_information"]
    assert len(messages) == 2 and "טמפרטורה" in messages[0] and "כמה זמן" in messages[1]
    paper = draft_for("עוגיות\nקמח\nמניחים על נייר אפייה ומקררים.", ["title", "ingredient", "step"],
                      title="עוגיות", title_written_in_text=True)
    assert "missing_information" not in kinds(paper)  # baking paper is not baking


def test_a_tip_inside_the_ingredient_list_is_pointed_out_as_a_possible_ingredient():
    source = "עוגה\n2 כוסות קמח\nקרם לקישוט\nאופים 30 דקות ב-180 מעלות."
    draft = draft_for(source, ["title", "ingredient", "tip", "step"], title="עוגה", title_written_in_text=True)
    [point] = [issue for issue in draft.issues if issue.kind == "other"]
    assert point.quote == "קרם לקישוט" and "נשמרה כהערה" in point.message


def test_a_title_said_to_be_written_must_start_a_line_otherwise_it_counts_as_composed():
    source = "מי לא אוהב שקשוקה?\n4 ביצים\nמבשלים 10 דקות."
    draft = draft_for(source, ["not_recipe", "ingredient", "step"], title="שקשוקה", title_written_in_text=True)
    assert draft.title == "שקשוקה" and "missing_title" in kinds(draft)


def test_either_kind_of_answer_becomes_a_draft():
    assert make_draft(answer(), DRINK, CATEGORIES).step_groups[0].steps == ["לערבל הכל יחד עד קבלת משקה ולרוויה!"]


# --- The local extractor in reference mode ------------------------------------------------------------


DESSERTS = {"fit": "clear", "category_id": 1, "subcategory_id": None, "candidate_category_ids": []}


def local_model(*chat_replies: tuple[int, dict | None]):
    """A fake Ollama: each chat request gets the next (status, answer); the requests are kept."""
    requests: list[dict] = []
    replies = list(chat_replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/show":
            return httpx2.Response(200, json={"capabilities": ["completion"]})
        requests.append(json.loads(request.content))
        status, reply = replies.pop(0)
        message = {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)}
        body = {"message": message, "done_reason": "stop", "prompt_eval_count": 1500, "eval_count": 120}
        return httpx2.Response(status, json=body if status == 200 else {"error": "CUDA error"})

    client = httpx2.Client(transport=httpx2.MockTransport(handle))
    extractor = OllamaExtractor(base_url="http://127.0.0.1:11434", model="qwen3:8b", context_tokens=8192, timeout=60, client=client)
    return extractor, requests


def test_the_local_extractor_sends_passages_reads_back_labels_and_asks_for_the_category_separately():
    first = answer().model_dump()  # no category fits, it says
    extractor, requests = local_model((200, first), (200, {"dish": "a sweet drink", "classification": DESSERTS}))
    output = extractor.extract(DRINK, CATEGORIES)

    assert isinstance(output, ReferenceOutput)
    labels, classify = requests
    keys = [passage_key(DRINK, segment) for segment in segment_text(DRINK)]
    assert labels["format"] == reference_schema(CATEGORIES, keys)  # every passage, in order
    assert "[4] חצי תמר מג׳הול" in labels["messages"][1]["content"]
    system = labels["messages"][0]["content"]
    assert system.startswith(REFERENCE_SYSTEM_PROMPT)
    assert "[4] חצי תמר מג׳הול" not in system  # the instructions do not repeat the text
    assert extractor.last_raw == json.dumps(first, ensure_ascii=False)
    # The second request classifies the finished draft: its copied lines, not the numbered text.
    assert classify["messages"][0]["content"].startswith(CLASSIFY_SYSTEM_PROMPT)
    assert "חצי תמר מג׳הול" in classify["messages"][1]["content"] and "[4]" not in classify["messages"][1]["content"]
    assert output.classification.category_id == 1 and output.dish == "a sweet drink"
    assert extractor.last_usage == {"input_tokens": 3000, "output_tokens": 240}
    assert make_draft(output, DRINK, CATEGORIES).ingredient_groups[0].ingredients[0].text == "חצי תמר מג׳הול"


def test_if_the_category_request_fails_the_first_answers_category_stays():
    extractor, _ = local_model((200, answer().model_dump()), (500, None), (500, None))
    output = extractor.extract(DRINK, CATEGORIES)
    assert output.classification.fit == "no_fit"


def test_a_server_error_from_ollama_is_tried_once_more():
    reply = answer().model_dump()
    extractor, requests = local_model((500, None), (200, reply), (200, {"dish": "drink", "classification": DESSERTS}))
    assert extractor.extract(DRINK, CATEGORIES).classification.category_id == 1
    assert len(requests) == 3  # the failed request, its retry, the category


def test_a_yield_or_time_line_is_kept_as_a_note_with_its_label():
    source = "עוגה\nזמן אפייה: שעה\nMakes 8\n2 כוסות קמח\nאופים."
    roles = ["title", "info", "continues", "info", "ingredient", "step"]
    draft = draft_for(source, roles, title="עוגה", title_written_in_text=True)
    assert draft.notes == ["זמן אפייה: שעה", "Makes 8"]


def test_the_labels_decide_whether_the_text_holds_a_recipe():
    assert is_recipe(answer(is_recipe=False))  # it labeled ingredients and a step: a recipe after all
    review = "ביקרנו במסעדה.\nהיה טעים."
    assert not is_recipe(answer(review, ["not_recipe", "not_recipe"], is_recipe=False))
