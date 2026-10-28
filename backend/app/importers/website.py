"""Reading a recipe page from a website, for an import. No model here: fetching and recognizing only.

1. The address: http or https, a host name, the usual web ports; never this computer or a private
   network. Checked on every request, redirects included: before connecting (the host's DNS answers)
   and after (the address actually connected to, before anything is read).
2. The page: one GET, at most MAX_REDIRECTS redirects, MAX_PAGE_BYTES, PAGE_DEADLINE_S; HTML only. The
   client says what it is (USER_AGENT); it does not pretend to be a browser.
3. The recipe: the page's Schema.org Recipe data when it has it (JSON-LD, then microdata), in its own
   words. Otherwise the page's main text, with navigation, comments, advertisements and the like left
   out as far as their markup shows, for the same extraction as pasted text.

Everything read here is data from a stranger's page: it is never followed as instructions.
"""

from __future__ import annotations

import html as html_lib
import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx2
from bs4 import BeautifulSoup, Tag

USER_AGENT = "RecipeNotebook/0.5 (a personal recipe notebook; reads one page when its owner imports it)"
MAX_PAGE_BYTES = 3_000_000  # a recipe page is a few hundred KB
MAX_IMAGE_BYTES = 20_000_000  # as for any picture (app/media.py)
MAX_REDIRECTS = 5
PAGE_DEADLINE_S = 30.0  # the whole request, redirects included
TIMEOUT = httpx2.Timeout(20.0, connect=10.0)
MAX_TEXT_CHARACTERS = 20_000  # what an import reads (schemas.MAX_IMPORT_CHARACTERS)
MIN_TEXT_CHARACTERS = 80  # less than this is not a recipe page's text
HTML_TYPES = {"text/html", "application/xhtml+xml"}
HTML_ACCEPT = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"
IMAGE_ACCEPT = "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8"

# Names that never lead to a public website.
LOCAL_NAMES = re.compile(r"(^|\.)(localhost|local|internal|intranet|lan|home|corp|localdomain|home\.arpa)\.?$", re.I)
# Tracking parameters, which do not change the page (dropped when comparing addresses).
TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|igsh|igshid|mc_cid|mc_eid|ref|ref_src)$", re.I)


class WebsiteError(Exception):
    """Why a page could not be read: a short code for the page (website_<code>), a message for the API."""

    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _invalid(message: str) -> WebsiteError:
    return WebsiteError("invalid_url", message, 422)


def _forbidden() -> WebsiteError:
    return WebsiteError("forbidden_address", "The address leads to this computer or to a private network, which is never read.", 422)


# --- The address --------------------------------------------------------------------------------------


def _with_scheme(text: str) -> str:
    """An address pasted without "https://" ("example.com/cake") gets it."""
    value = text.strip()
    return value if re.match(r"^[a-z][a-z0-9+.-]*:", value, re.I) else f"https://{value}"


def is_instagram(text: str) -> bool:
    """Whether a link is Instagram's (the Instagram importer reads it), by its host name alone."""
    try:
        host = (urlsplit(_with_scheme(text)).hostname or "").lower()
    except ValueError:
        return False
    return host in ("instagram.com", "instagr.am") or host.endswith((".instagram.com", ".instagr.am"))


def check_url(text: str) -> str:
    """The address as it will be fetched (lower-case scheme and host, no fragment), or WebsiteError."""
    value = _with_scheme(text)
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise _invalid("This is not a valid web address.") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise _invalid("Only http:// and https:// addresses can be read.")
    if parts.username is not None or parts.password is not None:
        raise _invalid("An address with a user name or a password is not read.")
    host = (parts.hostname or "").lower()
    if not host:
        raise _invalid("The address has no host name.")
    if port not in (None, 80, 443):
        raise WebsiteError("forbidden_address", "Only the usual web ports (80 and 443) are read.", 422)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not is_public(str(literal)):
            raise _forbidden()
    elif "." not in host or LOCAL_NAMES.search(host):
        raise _forbidden()
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def page_key(url: str) -> str:
    """What makes two addresses the same page: the host without "www.", the path without a final "/",
    and the query without tracking parameters (http or https alike)."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)))
    return f"{host}{parts.path.rstrip('/') or '/'}{'?' + query if query else ''}"


def is_public(address: str) -> bool:
    """Whether an IP address is on the public internet: not this computer, a private or shared network,
    link-local, multicast or reserved."""
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


Resolver = Callable[[str], list[str]]


def system_resolver(host: str) -> list[str]:
    """The host's addresses, as the operating system resolves them."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise WebsiteError("unreachable", f"The address {host} could not be found.") from None
    return sorted({str(info[4][0]) for info in infos})


def _ensure_public(host: str, resolve: Resolver) -> None:
    try:
        addresses = [str(ipaddress.ip_address(host.strip("[]")))]
    except ValueError:
        addresses = resolve(host)
    if not addresses:
        raise WebsiteError("unreachable", f"The address {host} could not be found.")
    if not all(is_public(address) for address in addresses):
        raise _forbidden()


# --- Fetching -----------------------------------------------------------------------------------------


@dataclass
class Page:
    url: str  # where it was read, after any redirects
    html: str


def _decode(body: bytes, charset: str | None) -> str:
    meta = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", body[:4096], re.I)
    for encoding in (charset, meta.group(1).decode("ascii", "ignore") if meta else None, "utf-8"):
        if encoding:
            try:
                return body.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
    return body.decode("utf-8", errors="replace")


def _check_status(status: int) -> None:
    if status in (401, 403, 429, 451):
        raise WebsiteError("blocked", f"The site refused to send the page (HTTP {status}).")
    if status in (404, 410):
        raise WebsiteError("not_found", f"The site says there is no such page (HTTP {status}).")
    if status >= 400:
        raise WebsiteError("http_error", f"The site answered with an error (HTTP {status}).")


class WebReader:
    """Reads pages and pictures from public websites, within the limits above.

    Tests give it a transport and a resolver of their own, and verify_peer=False: a stand-in transport
    has no network connection whose address could be checked."""

    def __init__(self, transport: httpx2.BaseTransport | None = None, resolve: Resolver = system_resolver, verify_peer: bool = True) -> None:
        self.transport = transport
        self.resolve = resolve
        self.verify_peer = verify_peer

    def page(self, url: str) -> Page:
        final, content_type, body, charset = self._get(url, HTML_ACCEPT, MAX_PAGE_BYTES)
        if content_type and content_type not in HTML_TYPES:
            raise WebsiteError("not_html", f"The address is not a web page ({content_type}).", 422)
        return Page(url=final, html=_decode(body, charset))

    def image(self, url: str) -> bytes:
        _, content_type, body, _ = self._get(url, IMAGE_ACCEPT, MAX_IMAGE_BYTES)
        if content_type and not content_type.startswith("image/"):
            raise WebsiteError("not_an_image", f"The picture's address is not a picture ({content_type}).")
        return body  # its real type is read from its first bytes when it is saved (app/media.py)

    def _get(self, url: str, accept: str, max_bytes: int) -> tuple[str, str, bytes, str | None]:
        current = check_url(url)
        deadline = time.monotonic() + PAGE_DEADLINE_S
        headers = {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "he,en;q=0.8"}
        # trust_env=False: straight to the site (a proxy's address would hide where the request went).
        with httpx2.Client(transport=self.transport, timeout=TIMEOUT, follow_redirects=False, headers=headers, trust_env=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                _ensure_public(urlsplit(current).hostname or "", self.resolve)
                try:
                    with client.stream("GET", current) as response:
                        self._check_peer(response)
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location:
                                raise WebsiteError("http_error", "The site redirected without saying where.")
                            current = check_url(urljoin(current, location))
                            continue
                        _check_status(response.status_code)
                        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                        length = response.headers.get("content-length", "")
                        if length.isdigit() and int(length) > max_bytes:
                            raise WebsiteError("too_large", f"The page is too large to read (over {max_bytes // 1_000_000} MB).")
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body += chunk
                            if len(body) > max_bytes:
                                raise WebsiteError("too_large", f"The page is too large to read (over {max_bytes // 1_000_000} MB).")
                            if time.monotonic() > deadline:
                                raise WebsiteError("timeout", "The site did not finish sending the page in time.", 504)
                        return current, content_type, bytes(body), response.charset_encoding
                except httpx2.TimeoutException:
                    raise WebsiteError("timeout", "The site did not answer in time.", 504) from None
                except httpx2.HTTPError as error:
                    first_line = (str(error).splitlines() or [type(error).__name__])[0]
                    raise WebsiteError("unreachable", f"The site could not be reached: {first_line}") from None
                finally:
                    if time.monotonic() > deadline:
                        raise WebsiteError("timeout", "The site did not answer in time.", 504)
        raise WebsiteError("too_many_redirects", f"The site redirected more than {MAX_REDIRECTS} times.")

    def _check_peer(self, response: httpx2.Response) -> None:
        """The address actually connected to, before anything is read: public, or nothing is used."""
        if not self.verify_peer:
            return
        stream = response.extensions.get("network_stream")
        address = stream.get_extra_info("server_addr") if stream is not None else None
        if not address or not is_public(str(address[0])):
            raise _forbidden()


# --- The recipe in the page's own data (Schema.org) ---------------------------------------------------


@dataclass
class StructuredRecipe:
    title: str
    ingredients: list[str]
    step_groups: list[tuple[str | None, list[str]]]
    servings: str | None
    times: dict[str, str]  # "זמן הכנה" -> "20 דקות"
    authors: list[str]
    image: str | None
    description: str | None
    found_in: str  # "json_ld" or "microdata"
    raw: dict[str, Any] = field(repr=False)

    @property
    def steps(self) -> list[str]:
        return [step for _, steps in self.step_groups for step in steps]


# A site's "are you a robot?" page instead of the page asked for (seen live: Radware's, on perfdrive.com).
BLOCK_PAGE = re.compile(
    r"captcha|are you a (ro)?bot|you are a bot|made us think that you are a bot|verify (that )?you are (a )?human|"
    r"access denied|attention required|just a moment\.\.\.|unusual traffic|checking your browser|perfdrive|radware|"
    r"incapsula|datadome|px-captcha|cf-chl",
    re.I,
)


def is_block_page(soup: BeautifulSoup) -> bool:
    """Whether the page is a bot check (its title, or the start of its text, says so)."""
    title = soup.find("title")
    head = " ".join([title.get_text(" ") if title else "", (soup.body or soup).get_text(" ", strip=True)[:1500]])
    return bool(BLOCK_PAGE.search(head))


@dataclass
class PageAnalysis:
    url: str  # the page's own address (its canonical link on the same site), else where it was read
    title: str | None
    site_name: str | None
    author: str | None  # from the page's metadata, when its recipe data names none
    image: str | None  # the page's declared main picture (og:image)
    recipe: StructuredRecipe | None
    ambiguous: list[str]  # the names of several recipes, none clearly the page's own
    text: str  # the main text, for the extraction when there is no recipe data
    truncated: bool
    blocked: bool = False  # a bot check came instead of the page


def _text(value: Any) -> str:
    """A string from the page's data as plain text: entities decoded, any HTML tags dropped, spaces collapsed."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str):
        return ""
    text = html_lib.unescape(value)
    if "<" in text:
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _type_names(node: dict[str, Any]) -> set[str]:
    names = set()
    for item in _listify(node.get("@type")):
        if isinstance(item, str):
            names.add(item.rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower())
    return names


def _walk(node: Any, depth: int = 0) -> Iterator[dict[str, Any]]:
    """Every object in a JSON-LD document (its @graph, mainEntity and the like included)."""
    if depth > 12:
        return
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value, depth + 1)
    elif isinstance(node, list):
        for item in node[:500]:
            yield from _walk(item, depth + 1)


def json_ld_documents(soup: BeautifulSoup) -> list[Any]:
    documents = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = (script.string or script.get_text() or "").strip()
        raw = re.sub(r"^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$", "", raw)
        try:
            documents.append(json.loads(raw, strict=False))
        except json.JSONDecodeError:
            continue
    return documents


_LEADING_NUMBER = re.compile(r"^\s*(\d{1,2}[.)]|step\s*\d{1,2}\s*[:.)-]|שלב\s*\d{1,2}\s*[:.)-])\s*", re.I)


def _step_lines(text: str) -> list[str]:
    """A step's text: one step per line; a leading "1." is the list's numbering, not its words."""
    return [_LEADING_NUMBER.sub("", line).strip() for line in _text(text).splitlines() if _LEADING_NUMBER.sub("", line).strip()]


def _instruction_groups(value: Any) -> list[tuple[str | None, list[str]]]:
    """recipeInstructions in any of its shapes: a string, strings, HowToStep, HowToSection, ItemList."""
    groups: list[tuple[str | None, list[str]]] = [(None, [])]

    def add(item: Any, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(item, str):
            groups[-1][1].extend(_step_lines(item))
        elif isinstance(item, list):
            for part in item:
                add(part, depth + 1)
        elif isinstance(item, dict):
            types = _type_names(item)
            if "howtosection" in types:
                groups.append((_text(item.get("name")) or None, []))
                add(item.get("itemListElement"), depth + 1)
                groups.append((None, []))
            elif item.get("text") or "howtostep" in types or "howtodirection" in types:
                groups[-1][1].extend(_step_lines(item.get("text") or item.get("name") or ""))
            elif "itemListElement" in item:
                add(item.get("itemListElement"), depth + 1)
            elif item.get("name"):
                groups[-1][1].extend(_step_lines(item.get("name")))

    add(value)
    return [(name, steps) for name, steps in groups if steps]


def _yield(value: Any) -> str | None:
    texts = [_text(item) for item in _listify(value)]
    texts = [text for text in texts if text]
    if not texts:
        return None
    worded = [text for text in texts if not text.replace(" ", "").isdigit()]
    return (worded or texts)[0][:200]


_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:\d+(?:\.\d+)?S)?)?$", re.I)


def duration_text(value: Any) -> str | None:
    """An ISO 8601 duration ("PT1H30M") in Hebrew ("שעה ו-30 דקות"); None when there is none."""
    match = _DURATION.match(_text(value).strip()) if isinstance(value, str) else None
    if match is None:
        return None
    days, hours, minutes = (int(part) if part else 0 for part in match.groups())
    hours += days * 24
    parts = []
    if hours:
        parts.append("שעה" if hours == 1 else "שעתיים" if hours == 2 else f"{hours} שעות")
    if minutes:
        parts.append("דקה" if minutes == 1 else f"{minutes} דקות")
    return " ו-".join(parts) or None


def _people(value: Any) -> list[str]:
    names = []
    for item in _listify(value):
        name = _text(item.get("name")) if isinstance(item, dict) else _text(item)
        if name and name not in names:
            names.append(name[:200])
    return names


def _image(value: Any, base: str) -> str | None:
    for item in _listify(value):
        url = item.get("url") or item.get("contentUrl") if isinstance(item, dict) else item
        if isinstance(url, str) and url.strip():
            return urljoin(base, url.strip())
    return None


def read_recipe(data: dict[str, Any], base: str, found_in: str) -> StructuredRecipe:
    """One Schema.org Recipe, in its own words (only HTML and numbering removed)."""
    ingredients: list[str] = []
    for item in _listify(data.get("recipeIngredient") or data.get("ingredients")):
        ingredients.extend(line for line in _text(item).splitlines() if line)
    times = {}
    for key, label in (("prepTime", "זמן הכנה"), ("cookTime", "זמן בישול"), ("totalTime", "זמן כולל")):
        text = duration_text(data.get(key))
        if text:
            times[label] = text
    description = _text(data.get("description")) or None
    return StructuredRecipe(
        title=_text(data.get("name")).replace("\n", " ")[:300],
        ingredients=ingredients,
        step_groups=_instruction_groups(data.get("recipeInstructions")),
        servings=_yield(data.get("recipeYield")),
        times=times,
        authors=_people(data.get("author")),
        image=_image(data.get("image"), base),
        description=description[:1000] if description else None,
        found_in=found_in,
        raw=data,
    )


def _microdata(scope: Tag) -> dict[str, Any]:
    """A Schema.org Recipe written as microdata (itemprop attributes), as a JSON-LD-like dict."""

    def value(tag: Tag) -> str:
        for attribute in ("content", "src", "href", "datetime"):
            if tag.has_attr(attribute) and tag.name in ("meta", "img", "link", "time", "a", "source"):
                return str(tag[attribute])
        return tag.get_text("\n")

    data: dict[str, Any] = {"@type": "Recipe"}
    for tag in scope.find_all(attrs={"itemprop": True}):
        props = str(tag.get("itemprop", "")).split()
        for prop in props:
            if prop in ("recipeIngredient", "ingredients"):
                data.setdefault("recipeIngredient", []).append(value(tag))
            elif prop == "recipeInstructions":
                items = tag.find_all("li") or tag.find_all(attrs={"itemprop": "text"})
                data.setdefault("recipeInstructions", []).extend(value(item) for item in items) if items else data.setdefault(
                    "recipeInstructions", []
                ).append(value(tag))
            elif prop == "author":
                name = tag.find(attrs={"itemprop": "name"})
                data.setdefault("author", []).append(value(name) if name else value(tag))
            elif prop in ("name", "recipeYield", "prepTime", "cookTime", "totalTime", "description", "image") and prop not in data:
                if prop == "name" and tag.find_parent(attrs={"itemscope": True}) is not scope:
                    continue  # the name of an author or a step, not of the recipe
                data[prop] = value(tag).strip()
    return data


def find_recipes(soup: BeautifulSoup, base: str) -> list[StructuredRecipe]:
    """Every Schema.org Recipe on the page: JSON-LD first, then microdata."""
    recipes = [read_recipe(node, base, "json_ld") for document in json_ld_documents(soup) for node in _walk(document) if "recipe" in _type_names(node)]
    if not recipes:
        scopes = soup.find_all(attrs={"itemscope": True, "itemtype": re.compile(r"schema\.org/Recipe/?$", re.I)})
        recipes = [read_recipe(_microdata(scope), base, "microdata") for scope in scopes]
    usable, seen = [], set()
    for recipe in recipes:
        key = (recipe.title.lower(), recipe.ingredients[0].lower() if recipe.ingredients else "")
        if (recipe.ingredients or recipe.steps) and key not in seen:
            seen.add(key)
            usable.append(recipe)
    return usable


def _norm(text: str | None) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def choose_recipe(recipes: list[StructuredRecipe], page_names: list[str]) -> tuple[StructuredRecipe | None, list[str]]:
    """The page's own recipe: the only one, or the one its heading or title names. Several, none of
    them named: none, and their names (the page is ambiguous; nothing is merged)."""
    if len(recipes) <= 1:
        return (recipes[0] if recipes else None), []
    names = [_norm(name) for name in page_names if _norm(name)]
    named = [r for r in recipes if _norm(r.title) and any(_norm(r.title) in name or name in _norm(r.title) for name in names)]
    if len(named) == 1:
        return named[0], []
    return None, [recipe.title or "(ללא שם)" for recipe in recipes]


# --- The page's main text, when it has no recipe data -------------------------------------------------

NOISE = re.compile(
    r"comment|sidebar|related|share|sharing|social|newsletter|subscribe|advert|\bads?\b|adsbygoogle|sponsor|promo|"
    r"cookie|consent|popup|modal|breadcrumb|widget|banner|navbar|\bmenu\b|footer|jump-to|print|rating|author-box|"
    r"more-recipes|you-may|recommend|tags?-list|\bnav\b",
    re.I,
)
RECIPE_CONTAINER = re.compile(
    r"wprm-recipe-container|tasty-recipes(?!-)|mv-create-card|recipe-card(?!-)|easyrecipe|recipe-content|recipe-body|"
    r"recipe-container|entry-content|post-content|article-content|article-body",
    re.I,
)
BLOCKS = ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "ul", "ol", "blockquote", "pre", "figcaption", "dd", "dt", "table"]


def _classes(tag: Tag) -> str:
    return " ".join([*tag.get("class", []), str(tag.get("id", ""))]) if tag.attrs else ""


def _main_block(soup: BeautifulSoup) -> Tag | None:
    """The element that holds the page's main content: its largest recipe or post container, else its
    largest article, else its main element, else its heading."""
    containers = [tag for tag in soup.find_all(True) if RECIPE_CONTAINER.search(_classes(tag))]
    for group in (containers[:20], soup.find_all("article")):
        if group:
            return max(group, key=lambda tag: len(tag.get_text(" ", strip=True)))
    return soup.find("main") or soup.find("h1")


def main_text(html: str, title: str | None) -> tuple[str, bool]:
    """The page's main text as lines, without its navigation, comments, advertisements and the like;
    whether it was cut at MAX_TEXT_CHARACTERS."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe", "form", "button", "select", "input",
                     "textarea", "canvas", "video", "audio", "picture", "object", "embed", "nav", "aside"]):
        tag.decompose()
    for tag in soup.find_all(["header", "footer"]):
        if not tag.decomposed and tag.find_parent(["article", "main"]) is None:
            tag.decompose()
    for tag in soup.find_all(attrs={"role": re.compile(r"navigation|banner|contentinfo|complementary|search|dialog|alert", re.I)}):
        if not tag.decomposed:
            tag.decompose()
    # The main content, and every element around it, is never noise, whatever its name: a theme's layout
    # wrappers can carry a noise word (seen live: "penci_is_nosidebar" and "theiaStickySidebar" around a whole post).
    block = _main_block(soup)
    around = {id(tag) for tag in (block, *block.parents)} if block is not None else set()
    for tag in soup.find_all(True):
        if tag.decomposed or tag.name in ("html", "body", "main", "article") or id(tag) in around:
            continue
        classes = _classes(tag)
        if classes and NOISE.search(classes) and not RECIPE_CONTAINER.search(classes):
            tag.decompose()
    candidates = [tag for tag in soup.find_all(True) if not tag.decomposed and RECIPE_CONTAINER.search(_classes(tag))]
    articles = soup.find_all("article")
    if candidates:
        root = max(candidates[:20], key=lambda tag: len(tag.get_text(" ", strip=True)))
    elif articles:
        root = max(articles, key=lambda tag: len(tag.get_text(" ", strip=True)))
    else:
        root = soup.find("main") or soup.body or soup
    for br in root.find_all("br"):
        br.replace_with("\n")
    for tag in root.find_all(BLOCKS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = [re.sub(r"[ \t ​]+", " ", line).strip() for line in root.get_text().splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if title and _norm(title) and _norm(title) not in _norm(text[:600]):
        text = f"{title}\n\n{text}"
    if len(text) <= MAX_TEXT_CHARACTERS:
        return text, False
    cut = text.rfind("\n", 0, MAX_TEXT_CHARACTERS)
    return text[: cut if cut > MAX_TEXT_CHARACTERS // 2 else MAX_TEXT_CHARACTERS], True


# --- The page as a whole -------------------------------------------------------------------------------


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag is not None and _text(tag.get("content")):
            return _text(tag.get("content"))
    return None


def _canonical(soup: BeautifulSoup, read_at: str) -> str:
    link = soup.find("link", rel=lambda value: value and "canonical" in (value if isinstance(value, list) else value.split()))
    href = link.get("href") if link is not None else None
    if isinstance(href, str) and href.strip():
        try:
            candidate = check_url(urljoin(read_at, href.strip()))
        except WebsiteError:
            return read_at
        same_site = (urlsplit(candidate).hostname or "").removeprefix("www.") == (urlsplit(read_at).hostname or "").removeprefix("www.")
        return candidate if same_site else read_at
    return read_at


def _article_author(documents: list[Any]) -> str | None:
    for document in documents:
        for node in _walk(document):
            if _type_names(node) & {"article", "blogposting", "newsarticle", "webpage"}:
                names = _people(node.get("author"))
                if names:
                    return names[0]
    return None


def analyze(page: Page) -> PageAnalysis:
    soup = BeautifulSoup(page.html, "html.parser")
    url = _canonical(soup, page.url)
    heading = soup.find("h1")
    title_tag = soup.find("title")
    og_title = _meta(soup, "og:title")
    page_title = re.split(r"\s+[|\-–—]\s+", _text(title_tag.get_text()) if title_tag else "")[0] or None
    h1 = _text(heading.get_text(" ")) if heading is not None else None
    recipes = find_recipes(soup, url)
    recipe, ambiguous = choose_recipe(recipes, [name for name in (h1, og_title, page_title) if name])
    blocked = recipe is None and not ambiguous and is_block_page(soup)
    text, truncated = ("", False) if recipe is not None or blocked else main_text(page.html, h1 or og_title or page_title)
    image = _meta(soup, "og:image", "og:image:url", "twitter:image")
    return PageAnalysis(
        url=url,
        title=h1 or og_title or page_title,
        site_name=_meta(soup, "og:site_name", "application-name"),
        author=_meta(soup, "author", "article:author") or _article_author(json_ld_documents(soup)),
        image=urljoin(url, image) if image else None,
        recipe=recipe,
        ambiguous=ambiguous,
        text=text,
        truncated=truncated,
        blocked=blocked,
    )


def render(recipe: StructuredRecipe) -> str:
    """The page's recipe data as readable text: what the review screen shows as the original."""
    parts = [recipe.title] if recipe.title else []
    if recipe.description:
        parts.append(recipe.description)
    facts = ([f"כמות: {recipe.servings}"] if recipe.servings else []) + [f"{label}: {value}" for label, value in recipe.times.items()]
    if facts:
        parts.append("\n".join(facts))
    if recipe.ingredients:
        parts.append("מצרכים\n" + "\n".join(recipe.ingredients))
    if recipe.steps:
        lines = []
        for name, steps in recipe.step_groups:
            if name:
                lines.append(name)
            lines.extend(f"{number}. {step}" for number, step in enumerate(steps, 1))
        parts.append("אופן ההכנה\n" + "\n".join(lines))
    return "\n\n".join(parts)


def trimmed(data: Any, limit: int = 60_000) -> Any:
    """The page's recipe data, kept with the original: as it was, unless it is very large."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    return data if len(text) <= limit else {"note": "too large to keep", "size": len(text)}
