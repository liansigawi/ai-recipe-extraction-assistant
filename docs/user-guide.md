# User guide

How to use the notebook page (http://localhost:5173, once the app runs: [setup.md](setup.md)). The
interface is in Hebrew; button names are quoted as they appear.

## The notebook page

- **Browse:** the home page is a gallery of every recipe, newest first: its cover picture (a video's
  still too), or, without one, its category's drawing on its category's color; its title, category,
  credit, "טיוטה" and "דוגמה" labels, and whether you cooked it. Click a card to open the recipe;
  **"כל המתכונים"** (or the browser's back button) returns to the gallery, where you were. The address
  shows which recipe is open (`#/recipes/12`), so a reload stays on it. Phones show two cards a row.
- **The top bar** is always there: the notebook's name (back to the gallery), the search, "מתכונים",
  "קטגוריות", and **"ייבוא מתכון"**. On a wide screen "ייבוא מתכון מקישור" is a strip above the gallery
  (the button moves to its link field); on a phone the strip opens from the button.
- **Already cooked:** every card says **"✓ כבר הכנתי"** (green) or **"טרם הכנתי"** in the picture's top
  corner. **The badge is a button**: a click, a tap, or Enter/Space changes the mark right there, without
  opening the recipe. If the active filter then hides the card, a note at the bottom says so and offers
  **"ביטול"**. In a recipe, the **"כבר הכנתי"** control beside the title marks it or clears the mark; it is
  saved at once, and **"ביטול"** under it undoes the change. Every recipe starts unmarked: nothing is
  guessed. The mark is separate from the category and from the draft status, and saving a recipe never
  changes it.
- **Search and filter:** the search box finds recipes by their title or an ingredient line (every word you
  type, anywhere; niqqud, case and ׳/' marks do not matter). Above the gallery: **"הכול / טרם הכנתי / כבר
  הכנתי"**, each with how many recipes it would show; the categories, with the same drawing and color as
  the cards (they wrap onto more rows when they do not fit; choosing one shows its subcategories, e.g.
  "עוגות", and for the desserts also **"קינוח בריא"**, which works together with a type), and "לא מסווג";
  and "הכול / מתכונים / טיוטות" (everything, saved recipes only, or drafts only). They all combine;
  "ניקוי" clears them, and the line under them says how many recipes match. Searching runs in the page:
  no request and no model. Typing a search on a recipe's page goes back to the gallery with the results.
- **Create:** "לכתוב מתכון חדש", in the import strip, opens an empty form. Only the title is required.
  Type each ingredient line as written, and copy its amount into the quantity box ("200 גרם" from "200 גרם
  קמח"); leave the quantity empty when the recipe gives none. The form refuses a quantity that is not in
  its line.
- **Edit:** "עריכה" opens the recipe in the same form. Rows can be added, moved (▲ ▼) and removed (✕). The
  category list offers only existing categories, or "לא מסווג" (not classified). A dessert also has
  **"קינוח בריא": כן / לא / לא נקבע**, separate from its type. Leaving the form with unsaved changes
  (another page, cancel, the back button, closing the tab) asks first.
- **Delete:** "מחיקה" asks first, in the page. Deleting cannot be undone.
- **Categories:** "קטגוריות" lists your categories and their subcategories, with how many recipes each
  holds. "עריכה" changes a name or a description; "+ הוספת תת-קטגוריה" adds a subcategory under a top-level
  category; "הוספת קטגוריה ראשית" adds a new one. **The descriptions are what the model classifies new
  imports by**, so say there what belongs in the category. Renaming never moves a recipe; a recipe's
  category is changed in its editor. Subcategories are one level deep, and a name must be new among its
  siblings. Deleting a category is not offered yet.
- **Pictures and videos:** a card shows the recipe's cover picture, and the recipe's page shows it large
  at the top. In the recipe, "תמונות וסרטונים" shows them in the post's order, then your own; click one to
  see it large ("הקודם", "הבא", or the arrow keys; Escape closes). A video plays only when you press play.
  "קביעה כתמונה ראשית" makes a picture, or a video's still, the card's cover; "ביטול הבחירה כתמונה ראשית"
  goes back to the first picture. "הסרה מהמתכון" asks first. **"העלאת תמונה"** adds pictures from this
  computer (JPEG, PNG, WebP or GIF, up to 20 MB each) to any recipe. A video marked **"▶ באינסטגרם
  בלבד"** (dashed outline) was not saved here: its still is, with a link to watch it in the post; a video
  marked "▶ סרטון" is saved and plays offline. A file missing from the media folder shows "התמונה לא
  נמצאה" in its place.
- **Samples:** a new notebook starts with four invented sample recipes, labeled "דוגמה". They are not
  based on real recipes. Edit or delete them like any recipe; once deleted, they are not added again.

## Import a recipe from pasted text

The import uses the model you set up ([setup.md](setup.md#choose-how-imported-text-is-read)): the local
model or the Claude API. If the model is not available, the import screen says why (Ollama not running,
its model not downloaded, or no API key) and offers **"שמירה בלי עיבוד"** (save without processing), which
keeps the text as a draft for you to fill in.

1. **"להדביק טקסט של מתכון"**, in the import strip above the gallery (on a phone, press "ייבוא מתכון"
   first): paste a recipe into **"טקסט המתכון"**, for example an Instagram caption or text copied from a
   website, and press **"קריאה עם המודל המקומי"** (or **"קריאה עם Claude"**). It usually takes less than a
   minute.
2. The draft opens for **review**. At the top is the original text exactly as you pasted it (it stays in
   view while you scroll), then the points to check, then the editable form. Points can be: a passage the
   model could not place, a quantity not written in its line (left empty), an ingredient that only the
   steps mention, missing or unclear information, and the category. The model may only choose one of your
   existing categories; when it is not clear, the recipe stays "לא מסווג" with an explanation. Nothing
   ever creates a category.
3. Fix what needs fixing and decide each point. An ingredient that only the steps mention ("תותים
   מופיעים בהוראות ההכנה") quotes its sentence and shows the line it would add: the step's own words, with
   an amount only when the step writes one right before them. **"הוספת תותים למצרכים"** adds that line,
   labeled **"נוסף מהוראות ההכנה"** (an ordinary line: edit, move or remove it); **"התעלמות"** dismisses
   the point for this recipe only, adding nothing. If the list already has it, the point offers **"טופל"**
   instead; every other point is marked **"טופל"** (handled). Each decision is listed under **"הוחלט
   בבדיקה"** with **"ביטול"** (undo), marked "לא נשמר עדיין" until a save keeps it. Nothing is added without
   your click; the one exception is oil a step clearly fries or greases with, added as a line labeled
   "מופיע בהוראות ההכנה". Then:
   - **"שמירה כמתכון"** (save as recipe) saves it as a recipe. Only this button does that; Enter in a
     field never does.
   - **"שמירת טיוטה"** (save draft) keeps it as a draft, with the points still open, to continue later.
     Drafts are marked "טיוטה" in the list.

The original text is stored with the recipe and never changes when you edit it: open "הטקסט המקורי" in
the recipe view to see it.

## Import a recipe from an Instagram link

1. Paste the address of a public post or Reel into **"ייבוא מתכון מקישור"** above the gallery (on a
   phone, press "ייבוא מתכון" first), for example `https://www.instagram.com/p/DPbKEn-CnUt/`
   (`/reel/...` addresses and addresses with `?igsh=...` work too), and press **"ייבוא"**. It usually
   takes under a minute: a few seconds to read the post, then the same extraction as for pasted text.
   Instagram import needs Playwright's Chromium ([setup.md](setup.md#install-tested-on-windows-11)).
2. The draft opens for review like a pasted one. "הטקסט המקורי" says it is the post's caption, links to
   the post, and shows the full caption as read. Under the title, the **credit**: the creator's display
   name and username as the post gives them, the username linking to the profile. The credit comes from
   the post, never from the model; you can edit it in the recipe's sources ("שם @שם_משתמש", separated by
   commas), for example when the posting account credits someone else.
3. The post's **pictures and videos** are saved with the draft, in the post's order. A long video can add
   a minute. If some could not be saved (too large, refused, or too slow), the draft is still created, with
   the review point "תמונות וסרטונים" saying how many were saved and why; a video that could not be saved
   keeps its still and a link to the post.

**When the post is already in the notebook** (in a draft or a recipe, as its original or as a source you
entered), the import stops before anything is read and lists those recipes, each with **"פתיחה"**, and
offers **"ייבוא עותק נוסף"** (import another copy). The same post is recognized whatever the form of its
address.

**When only a preview of the caption was read** (it may be cut off), it is put into the text box with a
warning. Compare it with the post and complete it; if you import it unchanged, the draft carries the point
"כיתוב חלקי". A caption in which the model found no recipe is also put into the text box, to try again or
save without processing.

The importer reads one post you paste, as a logged-out visitor: it never logs in, uses your browser's
cookies, disguises itself or retries in loops. How it reads a post:
[architecture.md](architecture.md#import-flow-milestone-5-an-instagram-link).

### Add pictures and videos to a recipe you already have

Open the recipe and press **"שליפת מדיה מהפוסט"** under "תמונות וסרטונים". It appears when the recipe has
an Instagram post: its imported original, or an Instagram link in its sources (add one in the editor if
needed). It reads the post again and saves only its pictures and videos: the title, ingredients, steps,
categories, credit and your cover choice stay as they are. The line under the button says what happened
("בפוסט 3 פריטים. 2 נשמרו עכשיו. …", with "פרטים" for the reasons). Pressing it again adds nothing twice;
it retries only what is missing, such as a video kept as a still.

## Import a recipe from a website

Paste the page's address into **"ייבוא מתכון מקישור"** (or "קישור למתכון" on the import screen) and press
**"ייבוא"**. Any address that is not Instagram's goes to the website importer:

1. **The page's own recipe data first.** Most recipe sites describe their recipe for search engines
   (Schema.org). When the page has it, the draft is made from it **word for word**: no model writes any of
   it, and the model only chooses an existing category (or none). This takes seconds.
2. **Otherwise the page's main text**, without its menus, ads, related posts and comments as far as the
   page's markup shows them, goes through the same extraction as pasted text.
3. The draft opens for review. "הטקסט המקורי" says which it was ("נתוני המתכון שבדף" or "הטקסט הראשי של
   הדף"), links to the page, and shows exactly what was read. The **credit** is the page's author, else the
   site's name, editable like any credit. The page's **main picture** becomes the cover.

The same page imported again is noticed before it is read, as for Instagram posts. Which sites were tried,
and what is not supported: [website-import.md](website-import.md).

## When an import does not work

Nothing is saved when an import fails, and what you pasted or linked stays in its field (pasted text is
kept in this browser until an import succeeds). The page says why, in Hebrew.

| What the page says (in short) | What to do |
|---|---|
| It cannot reach the server | Start the backend ([setup.md](setup.md#run-the-app)), then "נסו שוב". |
| No model is available (Ollama not running, model missing, or no API key) | Fix it as the message says ([setup.md](setup.md#choose-how-imported-text-is-read)), or use "שמירה בלי עיבוד". |
| The time ran out | Try again. A local import waits at most 5 minutes by default, and stops if the computer slept past that. |
| The Instagram post is not available, needs a login, has no caption, or Instagram asks to wait | Copy the caption from the post, paste it into the text box and import it from there; the link is kept with the recipe as its source. Private posts and share links (`instagram.com/share/...`) cannot be read: open a share link and copy the post's own address. |
| The website refused, has no recipe, builds its recipe with scripts, or shows several recipes | Paste the recipe's text instead; the link is kept as its source. Details: [website-import.md](website-import.md#limits). |
| The text is not a recipe | Check that the whole recipe was pasted, or save it without processing. |
