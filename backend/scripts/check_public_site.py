"""Check the published notebook in a real browser, the way a visitor uses it (docs/public-notebook.md).

    uv run python -m scripts.check_public_site https://<project>.pages.dev

It reads only that address: no backend, no Ollama and no file of this computer is involved. It opens the
gallery, every recipe and comparison page by its direct link and again after a reload, searches, filters,
checks every picture, goes back with the browser's back button, looks at the pages at a phone's width, and
confirms that the site offers no way to change anything and accepts no change. Prints one line per check;
the exit code is 0 only when all of them passed.
"""

from __future__ import annotations

import re
import sys

import httpx2
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}
CHANGING_CONTROLS = ["ייבוא מתכון", "קטגוריות", "עריכה", "מחיקה", "בדיקה ושמירה", "העלאת תמונה", "שליפת מדיה מהפוסט"]


class Checks:
    def __init__(self) -> None:
        self.failed = 0

    def __call__(self, ok: bool, what: str, detail: str = "") -> bool:
        print(f"{'OK  ' if ok else 'FAIL'}  {what}{'' if ok or not detail else f': {detail}'}")
        self.failed += not ok
        return ok


def open_page(page: Page, url: str) -> None:
    page.goto(url)
    page.wait_for_load_state("networkidle")


def images_loaded(page: Page) -> tuple[int, list[str]]:
    """How many pictures the page shows, and the ones that did not load. The pictures load lazily, as they
    come near the screen: the page is scrolled to its end first, as a visitor would, and back to the top."""
    page.evaluate(
        """async () => {
            for (let y = 0; y < document.documentElement.scrollHeight; y += 600) {
                window.scrollTo(0, y)
                await new Promise((resolve) => setTimeout(resolve, 60))
            }
            window.scrollTo(0, 0)
        }"""
    )
    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_function("[...document.images].every((i) => i.complete)", timeout=30_000)
    except PlaywrightTimeout:
        pass  # the ones still loading are reported below
    state = page.evaluate("[...document.images].map(i => [i.currentSrc || i.src, i.complete && i.naturalWidth > 0])")
    return len(state), [src for src, ok in state if not ok]


def categories_out_of_view(page: Page) -> list[str]:
    """The category filters a visitor cannot see whole without scrolling: any chip that is not entirely
    inside both the screen and its own row's visible box (a row that scrolls or clips would hide it)."""
    return page.evaluate(
        """() => {
            const width = document.documentElement.clientWidth;
            return [...document.querySelectorAll('.category-filter label.filter-chip')].filter((chip) => {
                const r = chip.getBoundingClientRect();
                const row = chip.parentElement.getBoundingClientRect();
                return r.width === 0 || r.left < -0.5 || r.right > width + 0.5 || r.left < row.left - 0.5 || r.right > row.right + 0.5;
            }).map((chip) => chip.innerText.trim());
        }"""
    )


def no_sideways_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    base = argv[0].rstrip("/") + "/"
    check = Checks()
    notebook = httpx2.get(f"{base}notebook.json", timeout=20, follow_redirects=True).json()
    recipes = notebook["recipes"]
    compared = [r for r in recipes if r.get("processing")]
    print(f"{base}: {len(recipes)} recipes, {len(compared)} comparison pages, exported {notebook['exported_at']}")

    # Nothing to change: a change sent to the site leaves it as it was, and there is no API.
    before = httpx2.get(f"{base}notebook.json", timeout=20, follow_redirects=True).content
    write = httpx2.post(f"{base}notebook.json", json={"recipes": []}, timeout=20)
    after = httpx2.get(f"{base}notebook.json", timeout=20, follow_redirects=True).content
    check(after == before, f"a change sent to the site changes nothing (it answered HTTP {write.status_code})")
    api = httpx2.get(f"{base}api/recipes", timeout=20, follow_redirects=True)
    check("json" not in api.headers.get("content-type", ""), "there is no API behind the site", api.headers.get("content-type", ""))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=DESKTOP)
        requests: list[tuple[str, str]] = []
        errors: list[str] = []
        page.on("request", lambda r: requests.append((r.method, r.url)))
        page.on("pageerror", lambda e: errors.append(str(e)))

        open_page(page, base)
        cards = page.locator(".recipe-card")
        check(cards.count() == len(recipes), "the gallery shows every published recipe", f"{cards.count()} of {len(recipes)}")
        shown, broken = images_loaded(page)
        check(not broken, f"the gallery's {shown} pictures load", ", ".join(broken))
        present = [name for name in CHANGING_CONTROLS if page.get_by_role("button", name=name, exact=True).count()]
        check(not present and page.locator("button.cooked-badge").count() == 0, "the gallery has no control that changes data", ", ".join(present))
        hidden = categories_out_of_view(page)
        check(not hidden, f"every category filter is in view at {DESKTOP['width']} px, none beyond the edge", ", ".join(hidden))

        # Search, then the filters.
        target = recipes[0]
        word = max(target["title"].split(), key=len)
        page.get_by_role("searchbox").fill(word)
        names = page.locator(".recipe-card-title").all_inner_texts()
        check(target["title"] in names and len(names) <= len(recipes), f'searching "{word}" finds its recipe', f"{len(names)} shown")
        page.get_by_role("searchbox").fill("אין-מתכון-כזה")
        check(cards.count() == 0 and page.get_by_text("לא נמצאו מתכונים").count() == 1, "a search with no match says so")
        page.get_by_role("searchbox").fill("")
        cooked = sum(r["cooked"] for r in recipes)
        page.locator("label.cooked-option-cooked").click()
        check(cards.count() == cooked, '"כבר הכנתי" shows the recipes marked as cooked', f"{cards.count()}, expected {cooked}")
        page.locator("label.cooked-option-all").click()
        for category in notebook["categories"]:
            page.locator(".category-filter label", has_text=category["name"]).click()
            expected = sum(r["category"] is not None and r["category"]["id"] == category["id"] for r in recipes)
            check(cards.count() == expected, f'the filter "{category["name"]}" shows its recipes', f"{cards.count()}, expected {expected}")
            for sub in category["subcategories"]:
                page.locator(".subcategory-filter label", has_text=sub["name"]).click()
                expected = sum(r["subcategory"] is not None and r["subcategory"]["id"] == sub["id"] for r in recipes)
                check(cards.count() == expected, f'the filter "{sub["name"]}" shows its recipes', f"{cards.count()}, expected {expected}")
            if category.get("healthy_style"):  # "קינוח בריא", with all of the category's types
                toggle = page.locator(".subcategory-filter label.is-toggle")
                if check(toggle.count() == 1, f'the filter "קינוח בריא" is offered with {category["name"]}'):
                    page.locator(".subcategory-filter label", has_text=f"כל ה{category['name']}").click()
                    toggle.click()
                    expected = sum(r["category"] is not None and r["category"]["id"] == category["id"] and r.get("healthy") is True for r in recipes)
                    check(cards.count() == expected, f'the filter "קינוח בריא" shows the healthy-style {category["name"]}', f"{cards.count()}, expected {expected}")
                    toggle.click()
        page.locator(".category-filter label", has_text="לא מסווג").click()
        expected = sum(r["category"] is None for r in recipes)
        check(cards.count() == expected, 'the filter "לא מסווג" shows the unclassified recipes', f"{cards.count()}, expected {expected}")
        page.locator(".category-filter label", has_text="הכול").click()

        # Every recipe by its own link, and again after a reload; the back button returns to the gallery.
        for recipe in recipes:
            open_page(page, f"{base}#/recipes/{recipe['id']}")
            page.reload()
            page.wait_for_load_state("networkidle")
            title = page.locator("h2.recipe-title").inner_text()
            shown, broken = images_loaded(page)
            changing = [name for name in CHANGING_CONTROLS if page.get_by_role("button", name=name, exact=True).count()]
            ok = title == recipe["title"] and not broken and not changing and page.locator("input[type=checkbox]").count() == 0
            check(ok, f"recipe {recipe['id']} opens by its link and after a reload, read-only, pictures loaded", f"title {title!r}, broken {broken}, controls {changing}")
        open_page(page, base)
        page.locator(".recipe-card-open").first.click()
        page.go_back()
        page.wait_for_load_state("networkidle")
        check(page.locator(".recipe-card").count() == len(recipes), "the back button returns from a recipe to the gallery")

        for recipe in compared:
            open_page(page, f"{base}#/recipes/{recipe['id']}/source")
            page.reload()
            page.wait_for_load_state("networkidle")
            original = page.get_by_role("region", name="הטקסט המקורי").inner_text()
            first_line = recipe["original"]["text"].strip().splitlines()[0].strip()
            classification = page.get_by_role("region", name="סיווג")
            check(classification.count() == 1 and classification.get_by_text("הצעת המודל לפני הבדיקה").count() == 1
                  and classification.get_by_text("הסיווג לאחר הבדיקה").count() == 1,
                  f"the comparison page of {recipe['id']} shows the model's classification before review and the one after it")
            if recipe["processing"].get("demonstration"):
                # Its demonstration is the comparison: the reviewed result beside the original, the draft folded, no controls.
                result = page.get_by_role("region", name="המתכון לאחר הבדיקה")
                controls = page.get_by_role("button", name=re.compile("^(הוספת|התעלמות|טופל|ביטול)"))
                ok = (first_line in original and result.count() == 1 and result.locator("li").count() > 0
                      and page.get_by_text("הצגת הטיוטה לפני הבדיקה").count() == 1 and controls.count() == 0)
                check(ok, f"the comparison page of {recipe['id']} shows its original and its demonstration, read-only")
                continue
            saved = page.get_by_role("region", name="המתכון השמור")
            ok = first_line in original and saved.count() == 1 and saved.locator("li").count() > 0
            check(ok, f"the comparison page of {recipe['id']} shows its original and its saved recipe")
        open_page(page, f"{base}#/about")
        check(page.get_by_role("heading", name="על מחברת המתכונים").count() == 1, "the page about the project opens by its link")

        sent = sorted({method for method, _ in requests})
        outside = sorted({url for _, url in requests if not url.startswith(base) and not url.startswith("data:")})
        check(sent == ["GET"], "the pages only read (every request a GET)", ", ".join(sent))
        check(not outside, "the pages load nothing from other sites", ", ".join(outside))
        check(not errors, "no script errors", "; ".join(errors))

        phone = browser.new_page(viewport=PHONE)
        open_page(phone, base)
        hidden = categories_out_of_view(phone)
        check(not hidden, f"every category filter is in view at a phone's width ({PHONE['width']} px)", ", ".join(hidden))
        addresses = [base, f"{base}#/about"] + [f"{base}#/recipes/{r['id']}" for r in recipes] + [f"{base}#/recipes/{r['id']}/source" for r in compared]
        wide = []
        for address in addresses:
            open_page(phone, address)
            if not no_sideways_scroll(phone):
                wide.append(address.removeprefix(base) or "gallery")
        check(not wide, f"at a phone's width ({PHONE['width']} px) no page scrolls sideways", ", ".join(wide))
        browser.close()

    print("All checks passed." if check.failed == 0 else f"{check.failed} check(s) failed.")
    return 0 if check.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
