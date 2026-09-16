"""JustDial via Playwright: category listing pages -> name, rating, reviews, address.

JustDial hides phone numbers behind a login, so phones here are usually empty;
enrichment and merging with Maps fill them in where possible.
"""

import json
from urllib.parse import quote, urlparse

from playwright.async_api import Browser
from playwright.async_api import Error as PlaywrightError
from selectolax.parser import HTMLParser, Node

from .models import Lead
from .utils import CONTEXT_OPTIONS, log, normalize_phone, parse_float, parse_int, polite_sleep

BASE_URL = "https://www.justdial.com"
MAX_PAGES = 20


def search_url(keyword: str, city: str) -> str:
    def part(text: str) -> str:
        return quote(text.strip().title().replace(" ", "-"))

    return f"{BASE_URL}/{part(city)}/{part(keyword)}"


def _jsonld_addresses(tree: HTMLParser) -> dict[str, str]:
    """Listing URL path -> full postal address, from the page's JSON-LD."""
    addresses: dict[str, str] = {}
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text())
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            url, address = item.get("url") or "", item.get("address")
            if not url or "/nct-" in url or not isinstance(address, dict):
                continue
            parts = (address.get(k) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode"))
            addresses[urlparse(url).path] = ", ".join(p.strip() for p in parts if p and p.strip())
    return addresses


def _text(card: Node, selector: str) -> str:
    node = card.css_first(selector)
    return node.text(strip=True) if node else ""


def parse_listing(html: str) -> tuple[list[Lead], str | None]:
    """Return (leads on this page, next page URL or None)."""
    tree = HTMLParser(html)
    addresses = _jsonld_addresses(tree)
    leads: list[Lead] = []
    for card in tree.css("div.resultbox"):
        anchor = card.css_first("a.resultbox_title_anchorbox")
        if not anchor:
            continue
        name = _text(card, ".resultbox_title_anchor") or (anchor.attributes.get("title") or "").strip()
        if not name:
            continue
        path = (anchor.attributes.get("href") or "").split("?")[0]
        lead = Lead(
            name=name,
            sources=["justdial"],
            listing_url=BASE_URL + path if path.startswith("/") else path,
            rating=parse_float(_text(card, ".resultbox_totalrate")),
            reviews=parse_int(_text(card, ".resultbox_countrate")),
        )
        lead.address = addresses.get(urlparse(lead.listing_url).path) or _text(card, ".resultbox_address")
        tel = card.css_first('a[href^="tel:"]')
        if tel:
            lead.phone = normalize_phone((tel.attributes.get("href") or "")[4:])
        leads.append(lead)

    next_link = tree.css_first('link[rel="next"]')
    return leads, (next_link.attributes.get("href") if next_link else None)


async def run(keyword: str, city: str, limit: int, sink: list[Lead], browser: Browser) -> None:
    context = await browser.new_context(**CONTEXT_OPTIONS)
    url: str | None = search_url(keyword, city)
    seen: set[str] = set()
    added = 0
    try:
        page = await context.new_page()
        for page_no in range(1, MAX_PAGES + 1):
            if not url or added >= limit:
                break
            await page.goto(url, wait_until="load", timeout=45_000)
            try:
                # Empty skeleton cards render first; wait for real, hydrated listings.
                await page.wait_for_function(
                    "document.querySelectorAll('div.resultbox a.resultbox_title_anchorbox').length >= 5",
                    timeout=20_000,
                )
            except PlaywrightError:
                log.warning("justdial: no listings on page %d (title: %r), stopping", page_no, await page.title())
                break
            await polite_sleep(1.5, 2.5)
            leads, url = parse_listing(await page.content())
            fresh = [lead for lead in leads if lead.listing_url not in seen]
            if not fresh:
                break
            for lead in fresh[: limit - added]:
                seen.add(lead.listing_url)
                sink.append(lead)
                added += 1
            await polite_sleep(3, 6)
    except PlaywrightError as exc:
        log.warning("justdial: stopped early: %s", str(exc).splitlines()[0])
    finally:
        await context.close()
        log.info("justdial: collected %d listings", added)
