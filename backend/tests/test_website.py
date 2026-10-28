"""Reading recipe pages from websites (app/importers/website.py), offline: addresses, the bounded fetch,
the page's Schema.org recipe data, and its main text. The pages are invented; a stand-in transport and
resolver answer for the network."""

import json

import httpx2
import pytest

from app.importers import website
from app.importers.website import WebReader, WebsiteError

PUBLIC = "93.184.216.34"  # an address on the public internet (example.com's)


def resolver(mapping: dict[str, str] | None = None):
    """Every host is public, unless the mapping says otherwise."""
    return lambda host: [(mapping or {}).get(host, PUBLIC)]


def reader(routes: dict[str, httpx2.Response | Exception], mapping: dict[str, str] | None = None, **options) -> WebReader:
    def handler(request: httpx2.Request) -> httpx2.Response:
        answer = routes.get(str(request.url))
        if answer is None:
            return httpx2.Response(404)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return WebReader(transport=httpx2.MockTransport(handler), resolve=resolver(mapping), verify_peer=options.get("verify_peer", False))


def html_page(body: str, head: str = "") -> httpx2.Response:
    return httpx2.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=f"<html><head>{head}</head><body>{body}</body></html>".encode())


# --- Addresses -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("HTTPS://Www.Example.co.il/recipe?id=3#top", "https://www.example.co.il/recipe?id=3"),
        ("example.com/cake", "https://example.com/cake"),  # pasted without https://
        ("https://xn--4dbrk0ce.example/מתכון", "https://xn--4dbrk0ce.example/מתכון"),
    ],
)
def test_an_address_is_tidied_but_not_changed(text, expected):
    assert website.check_url(text) == expected


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("ftp://example.com/x", "invalid_url"),
        ("javascript:alert(1)", "invalid_url"),
        ("https://user:secret@example.com/", "invalid_url"),
        ("http://localhost/admin", "forbidden_address"),
        ("http://127.0.0.1:80/", "forbidden_address"),
        ("http://10.1.2.3/", "forbidden_address"),
        ("http://192.168.1.1/", "forbidden_address"),
        ("http://169.254.169.254/latest/meta-data", "forbidden_address"),  # a cloud's metadata service
        ("http://[::1]/", "forbidden_address"),
        ("http://[::ffff:127.0.0.1]/", "forbidden_address"),
        ("http://printer.local/", "forbidden_address"),
        ("http://router/", "forbidden_address"),
        ("https://example.com:8000/", "forbidden_address"),  # only the usual web ports
    ],
)
def test_addresses_that_are_never_read(text, code):
    with pytest.raises(WebsiteError) as caught:
        website.check_url(text)
    assert caught.value.code == code


def test_public_and_private_ip_addresses():
    assert website.is_public("8.8.8.8") and website.is_public("2001:4860:4860::8888")
    for address in ("127.0.0.1", "10.0.0.1", "172.16.5.4", "192.168.0.10", "100.64.1.1", "169.254.0.1", "224.0.0.1", "::1", "fd00::1", "fe80::1", "0.0.0.0"):
        assert not website.is_public(address), address


def test_instagram_is_recognized_by_the_host_name_alone():
    assert website.is_instagram("https://www.instagram.com/p/Cm1mCdCpSzJ/")
    assert website.is_instagram("instagram.com/reel/x/")
    assert not website.is_instagram("https://instagram.com.example.net/p/x/")
    assert not website.is_instagram("https://example.com/instagram.com/p/x/")


def test_the_same_page_whatever_its_address_s_small_differences():
    same = ["https://www.example.com/cake/", "http://example.com/cake", "https://example.com/cake?utm_source=ig&fbclid=x"]
    assert len({website.page_key(url) for url in same}) == 1
    assert website.page_key("https://example.com/cake?id=2") != website.page_key("https://example.com/cake?id=3")


# --- Fetching --------------------------------------------------------------------------------------------


def test_a_page_is_read_with_its_redirects_each_one_checked():
    pages = reader({
        "https://example.com/r": httpx2.Response(301, headers={"location": "/recipes/cake"}),
        "https://example.com/recipes/cake": html_page("<h1>עוגה</h1>"),
    })
    page = pages.page("https://example.com/r")
    assert page.url == "https://example.com/recipes/cake" and "עוגה" in page.html


@pytest.mark.parametrize(
    ("location", "mapping"),
    [("http://127.0.0.1/admin", None), ("https://internal.example.net/", {"internal.example.net": "10.0.0.7"})],
)
def test_a_redirect_to_this_computer_or_a_private_network_is_not_followed(location, mapping):
    pages = reader({"https://example.com/r": httpx2.Response(302, headers={"location": location})}, mapping)
    with pytest.raises(WebsiteError) as caught:
        pages.page("https://example.com/r")
    assert caught.value.code == "forbidden_address"


def test_a_host_whose_name_resolves_to_a_private_address_is_not_read():
    with pytest.raises(WebsiteError) as caught:
        reader({}, {"recipes.example.org": "192.168.1.20"}).page("https://recipes.example.org/cake")
    assert caught.value.code == "forbidden_address"


def test_the_address_actually_connected_to_is_checked_too():
    """A stand-in has no network connection to check: with the check on, it fails closed."""
    with pytest.raises(WebsiteError) as caught:
        reader({"https://example.com/": html_page("x")}, verify_peer=True).page("https://example.com/")
    assert caught.value.code == "forbidden_address"


def test_too_many_redirects():
    routes = {f"https://example.com/{n}": httpx2.Response(302, headers={"location": f"/{n + 1}"}) for n in range(10)}
    with pytest.raises(WebsiteError) as caught:
        reader(routes).page("https://example.com/0")
    assert caught.value.code == "too_many_redirects"


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (httpx2.Response(403), "blocked"),
        (httpx2.Response(429), "blocked"),
        (httpx2.Response(404), "not_found"),
        (httpx2.Response(500), "http_error"),
        (httpx2.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"), "not_html"),
        (httpx2.Response(200, headers={"content-type": "text/html", "content-length": "9000000"}, content=b"x"), "too_large"),
        (httpx2.ReadTimeout("slow"), "timeout"),
        (httpx2.ConnectError("refused"), "unreachable"),
    ],
)
def test_why_a_page_could_not_be_read(answer, code):
    with pytest.raises(WebsiteError) as caught:
        reader({"https://example.com/cake": answer}).page("https://example.com/cake")
    assert caught.value.code == code


def test_a_page_larger_than_the_limit_is_stopped_while_it_streams(monkeypatch):
    monkeypatch.setattr(website, "MAX_PAGE_BYTES", 1000)
    page = httpx2.Response(200, headers={"content-type": "text/html"}, content=b"<p>" + b"x" * 5000)
    with pytest.raises(WebsiteError) as caught:
        reader({"https://example.com/big": page}).page("https://example.com/big")
    assert caught.value.code == "too_large"


def test_a_hebrew_page_in_windows_1255_is_decoded():
    body = '<html><head><meta charset="windows-1255"></head><body><h1>עוגת שוקולד</h1></body></html>'.encode("cp1255")
    page = reader({"https://example.co.il/": httpx2.Response(200, headers={"content-type": "text/html"}, content=body)}).page("https://example.co.il/")
    assert "עוגת שוקולד" in page.html


# --- The page's recipe data ---------------------------------------------------------------------------------

HEBREW_GRAPH = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "name": "המטבח של רותי"},
        {"@type": ["Recipe"], "name": "עוגת תפוזים &amp; שקדים",
         "author": {"@type": "Person", "name": "רותי כהן"},
         "image": [{"@type": "ImageObject", "url": "/images/cake.jpg"}],
         "recipeYield": ["10", "10 פרוסות"],
         "prepTime": "PT20M", "cookTime": "PT1H",
         "recipeIngredient": ["200 גרם קמח", "2 ביצים L", "<b>מיץ</b> מ-3 תפוזים", "קורט מלח"],
         "recipeInstructions": [
             {"@type": "HowToSection", "name": "לבצק", "itemListElement": [
                 {"@type": "HowToStep", "text": "1. מערבבים את הקמח עם הביצים."},
                 {"@type": "HowToStep", "text": "מוסיפים את מיץ התפוזים."}]},
             {"@type": "HowToSection", "name": "אפייה", "itemListElement": [
                 {"@type": "HowToStep", "text": "אופים 40 דקות ב-180 מעלות."}]},
         ]},
    ],
}

ENGLISH_ARRAY = [
    {"@type": "BreadcrumbList", "itemListElement": []},
    {"@context": "http://schema.org", "@type": "Recipe", "name": "Banana Bread",
     "author": [{"@type": "Person", "name": "Sam"}, {"@type": "Person", "name": "Alex"}],
     "image": "https://cdn.example.com/banana.jpg", "recipeYield": 8,
     "recipeIngredient": ["3 ripe bananas", "1/3 cup melted butter", "1 teaspoon baking soda"],
     "recipeInstructions": "Step 1: Mash the bananas.\nStep 2: Stir in the butter.\nBake for 55 minutes at 175°C."},
]


def ld(*documents) -> str:
    return "".join(f'<script type="application/ld+json">{json.dumps(document, ensure_ascii=False)}</script>' for document in documents)


def analyze(body: str, head: str = "", url: str = "https://example.co.il/cake") -> website.PageAnalysis:
    return website.analyze(website.Page(url=url, html=f"<html><head>{head}</head><body>{body}</body></html>"))


def test_json_ld_in_a_graph_with_sections_entities_and_html_is_read_in_its_own_words():
    result = analyze("<h1>עוגת תפוזים ושקדים</h1>", ld(HEBREW_GRAPH))
    recipe = result.recipe
    assert recipe is not None and recipe.found_in == "json_ld"
    assert recipe.title == "עוגת תפוזים & שקדים"
    assert recipe.ingredients == ["200 גרם קמח", "2 ביצים L", "מיץ מ-3 תפוזים", "קורט מלח"]
    assert recipe.step_groups == [("לבצק", ["מערבבים את הקמח עם הביצים.", "מוסיפים את מיץ התפוזים."]), ("אפייה", ["אופים 40 דקות ב-180 מעלות."])]
    assert recipe.servings == "10 פרוסות" and recipe.times == {"זמן הכנה": "20 דקות", "זמן בישול": "שעה"}
    assert recipe.authors == ["רותי כהן"] and recipe.image == "https://example.co.il/images/cake.jpg"
    assert result.text == ""  # the recipe data is enough: the page's text is not needed


def test_json_ld_with_one_string_of_numbered_steps():
    recipe = analyze("<h1>Banana Bread</h1>", ld(ENGLISH_ARRAY), url="https://example.com/banana").recipe
    assert recipe.step_groups == [(None, ["Mash the bananas.", "Stir in the butter.", "Bake for 55 minutes at 175°C."])]
    assert recipe.servings == "8" and recipe.authors == ["Sam", "Alex"]


def test_microdata_when_there_is_no_json_ld():
    body = """
    <div itemscope itemtype="http://schema.org/Recipe">
      <h1 itemprop="name">שקשוקה</h1>
      <span itemprop="author" itemscope itemtype="http://schema.org/Person"><span itemprop="name">דנה</span></span>
      <ul><li itemprop="recipeIngredient">4 ביצים</li><li itemprop="recipeIngredient">2 עגבניות</li></ul>
      <ol itemprop="recipeInstructions"><li>מטגנים את העגבניות.</li><li>שוברים פנימה את הביצים.</li></ol>
    </div>"""
    recipe = analyze(body).recipe
    assert recipe is not None and recipe.found_in == "microdata"
    assert (recipe.title, recipe.ingredients, recipe.steps, recipe.authors) == (
        "שקשוקה", ["4 ביצים", "2 עגבניות"], ["מטגנים את העגבניות.", "שוברים פנימה את הביצים."], ["דנה"])


def test_of_several_recipes_the_one_the_page_names_is_chosen():
    other = {"@type": "Recipe", "name": "Lemon Bars", "recipeIngredient": ["4 lemons"], "recipeInstructions": "Bake."}
    result = analyze("<h1>Banana Bread</h1>", ld(ENGLISH_ARRAY, other))
    assert result.recipe.title == "Banana Bread" and result.ambiguous == []


def test_several_recipes_none_of_them_named_are_ambiguous_and_never_merged():
    first = {"@type": "Recipe", "name": "Lemon Bars", "recipeIngredient": ["4 lemons"], "recipeInstructions": "Bake."}
    second = {"@type": "Recipe", "name": "Brownies", "recipeIngredient": ["cocoa"], "recipeInstructions": "Bake."}
    result = analyze("<h1>Our ten favourite desserts</h1>", ld(first, second))
    assert result.recipe is None and result.ambiguous == ["Lemon Bars", "Brownies"]


def test_recipe_data_with_neither_ingredients_nor_steps_is_not_used():
    result = analyze("<h1>x</h1><p>" + "טקסט ארוך על מתכון. " * 20 + "</p>", ld({"@type": "Recipe", "name": "ריק"}))
    assert result.recipe is None and "טקסט ארוך" in result.text


BLOG = """
<header class="site-header"><nav><a href="/">ראשי</a><a href="/desserts">קינוחים</a></nav></header>
<aside class="sidebar"><h3>מתכונים פופולריים</h3><ul><li>עוגת גבינה</li></ul></aside>
<main>
  <article class="post">
    <h1>עוגת תפוזים של סבתא</h1>
    <div class="share-buttons">שתפו בפייסבוק</div>
    <p>מתכון שכולם אוהבים, מהמחברת של סבתא.</p>
    <div class="ad-slot adsbygoogle">פרסומת</div>
    <h2>מצרכים</h2>
    <ul><li>200 גרם קמח</li><li>2 ביצים L</li><li>מלח</li></ul>
    <h2>אופן ההכנה</h2>
    <ol><li>מערבבים את כל החומרים.</li><li>אופים 30-35 דקות ב-180 מעלות.</li></ol>
    <div class="related-posts"><h3>אולי יעניין אתכם</h3><p>עוגיות שוקולד צ'יפס</p></div>
  </article>
  <section id="comments" class="comments-area"><p>איזה מתכון מעולה! תודה</p></section>
</main>
<footer><p>כל הזכויות שמורות</p></footer>
"""


def test_the_main_text_leaves_out_navigation_ads_related_posts_and_comments():
    result = analyze(BLOG, '<meta name="author" content="מירב"><meta property="og:image" content="/img/main.jpg"><meta property="og:site_name" content="הבלוג של מירב">')
    assert result.recipe is None
    lines = result.text.splitlines()
    for wanted in ("עוגת תפוזים של סבתא", "200 גרם קמח", "2 ביצים L", "מלח", "מערבבים את כל החומרים.", "אופים 30-35 דקות ב-180 מעלות."):
        assert wanted in lines, wanted
    for unwanted in ("ראשי", "מתכונים פופולריים", "שתפו בפייסבוק", "פרסומת", "אולי יעניין אתכם", "איזה מתכון מעולה! תודה", "כל הזכויות שמורות"):
        assert unwanted not in result.text, unwanted
    assert (result.author, result.site_name, result.image) == ("מירב", "הבלוג של מירב", "https://example.co.il/img/main.jpg")


RECIPE_IN_PARAGRAPHS = """
<p>הקדמה קצרה על הקינוח.</p>
<p><u>לקרם:</u><br> 500 מ"ל חלב<br> 3 כפות סוכר<br> 2 כפות קורנפלור</p>
<p><u>לציפוי:</u><br> 100 גרם שוקולד מריר</p>
<h1>אופן ההכנה:</h1>
<h1>קרם:</h1>
<ol><li>מחממים את החלב עם הסוכר.</li><li>מוסיפים קורנפלור ומבשלים עד להסמכה.</li></ol>
<h1>ציפוי:</h1>
<ol><li>ממיסים את השוקולד ויוצקים מעל הקרם.</li></ol>
<h1>הערות:</h1>
<ul><li>נשמר במקרר עד 3 ימים.</li></ul>
<div class="share-buttons">שתפו בפייסבוק</div>
"""
SIDEBAR = '<div class="sidebar widget-area"><h3>מתכונים פופולריים</h3><p>עוגת גבינה</p></div>'


@pytest.mark.parametrize(
    "layout",
    [
        # Seen live (oogio.net): the whole post column inside wrappers named for the sidebar it does not have.
        '<div class="container container-single penci_is_nosidebar"><div class="theiaStickySidebar"><article class="post">'
        '<h1>קרם וניל בכוסות</h1><div class="entry-content">{recipe}</div></article></div></div>'
        '<div class="penci-sidebar-content"><div class="theiaStickySidebar">{sidebar}</div></div>',
        # A common WordPress layout: the content and the sidebar side by side in one wrapper.
        '<div class="content-sidebar-wrap"><main class="content"><article class="post"><h1>קרם וניל בכוסות</h1>{recipe}'
        "</article></main>{sidebar}</div>",
    ],
    ids=["theme-wrappers", "content-sidebar-wrap"],
)
def test_the_main_text_inside_layout_wrappers_named_for_a_sidebar_keeps_its_lines_and_sections(layout):
    result = analyze(layout.format(recipe=RECIPE_IN_PARAGRAPHS, sidebar=SIDEBAR))
    assert [line for line in result.text.splitlines() if line] == [
        "קרם וניל בכוסות", "הקדמה קצרה על הקינוח.",
        "לקרם:", '500 מ"ל חלב', "3 כפות סוכר", "2 כפות קורנפלור", "לציפוי:", "100 גרם שוקולד מריר",
        "אופן ההכנה:", "קרם:", "מחממים את החלב עם הסוכר.", "מוסיפים קורנפלור ומבשלים עד להסמכה.",
        "ציפוי:", "ממיסים את השוקולד ויוצקים מעל הקרם.", "הערות:", "נשמר במקרר עד 3 ימים.",
    ]  # nothing from the sidebar or the share buttons


def test_a_bot_check_instead_of_the_page_is_recognized_and_not_read_as_text():
    body = "<h1>We are sorry...</h1><p>...but your activity and behavior on this website made us think that you are a bot.</p>"
    result = analyze(body, "<title>Radware Block Page</title>")
    assert result.blocked and result.text == ""
    assert not analyze(BLOG).blocked  # an ordinary page


def test_a_very_long_page_is_cut_at_the_import_limit(monkeypatch):
    monkeypatch.setattr(website, "MAX_TEXT_CHARACTERS", 500)
    result = analyze("<article><h1>מתכון</h1>" + "".join(f"<p>שורה מספר {n} של הטקסט</p>" for n in range(200)) + "</article>")
    assert result.truncated and len(result.text) <= 500


def test_the_canonical_address_of_the_same_site_is_used():
    head = '<link rel="canonical" href="https://www.example.co.il/recipes/cake/">'
    assert analyze("<p>x</p>", head, url="https://example.co.il/recipes/cake?utm_source=x").url == "https://www.example.co.il/recipes/cake/"
    elsewhere = '<link rel="canonical" href="https://other.example.net/cake">'
    assert analyze("<p>x</p>", elsewhere).url == "https://example.co.il/cake"


def test_the_recipe_data_as_readable_text_for_the_review_screen():
    text = website.render(analyze("<h1>x</h1>", ld(HEBREW_GRAPH)).recipe)
    assert text.splitlines()[:2] == ["עוגת תפוזים & שקדים", ""]
    assert "מצרכים\n200 גרם קמח\n2 ביצים L" in text
    assert "אופן ההכנה\nלבצק\n1. מערבבים את הקמח עם הביצים.\n2. מוסיפים את מיץ התפוזים.\nאפייה\n1. אופים" in text
    assert "כמות: 10 פרוסות" in text and "זמן בישול: שעה" in text
