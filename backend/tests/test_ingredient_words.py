"""Noticing an ingredient that the steps use and the ingredient list leaves out."""

from app.extraction.ingredient_words import only_in_steps


def words(lines: list[str], steps: list[str]) -> list[str]:
    return [written for written, _ in only_in_steps(lines, steps)]


def test_a_word_is_found_with_its_prefix_letters_and_shown_without_them():
    assert words(["2 כוסות קמח"], ["מוסיפים את הקמח ומקשטים בתותים."]) == ["תותים"]


def test_singular_plural_and_spelling_variants_count_as_listed():
    lines = ["3 בצלים", "שקדים פרוסים", "1 כפית אבקת אפייה", "2 tomatoes", "a handful of berries"]
    steps = ["מטגנים את הבצל, מצמידים שקד פרוס ומוסיפים אבקת אפיה.", "Slice the tomato and add a berry."]
    assert words(lines, steps) == []


def test_a_hebrew_plural_before_another_noun_counts_as_listing_the_ingredient():
    assert words(["נבטי חמניות להגשה", "4 עלי דפנה"], ["מוסיפים נבטים ומניחים את העלים."]) == []


def test_a_longer_name_is_one_ingredient_and_must_be_listed_as_such():
    assert words(["שמן קנולה"], ["מזלפים שמן זית."]) == ["שמן זית"]
    assert words(["3 כפות שמן זית"], ["מזלפים את שמן הזית, מוסיפים שמן זית."]) == []


def test_another_name_for_the_same_ingredient_counts_as_listed():
    assert words(["1 tsp ground coriander"], ["Add the cilantro."]) == []
    assert words(["כף ג'ינג'ר מגורד"], ["מוסיפים את הזנגביל."]) == []


def test_each_ingredient_is_pointed_out_once_at_its_first_step():
    found = only_in_steps(["2 cups flour"], ["Add the flour and the walnuts.", "Top with more walnuts."])
    assert found == [("walnuts", "Add the flour and the walnuts.")]


def test_what_the_dish_is_served_with_is_not_an_ingredient_left_out():
    assert words(["2 cups flour"], ["Bake. Serve the soup with crusty bread.", "מגישים לצד אורז לבן."]) == []
    assert words(["2 cups flour"], ["Top with feta."]) == ["feta"]
