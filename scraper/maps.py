"""Google Maps via Playwright: search -> scroll results feed -> open each place."""

import asyncio
import re
from urllib.parse import parse_qs, quote_plus, urlparse

from playwright.async_api import Browser, BrowserContext, Page
from playwright.async_api import Error as PlaywrightError
from selectolax.parser import HTMLParser

from .models import Lead
from .utils import CONTEXT_OPTIONS, is_social, log, normalize_phone, parse_float, parse_int, polite_sleep

SEARCH_URL = "https://www.google.com/maps/search/{query}?hl=en"
DETAIL_CONCURRENCY = 3
MAX_STALE_SCROLLS = 5
END_OF_LIST = "reached the end of the list"


def parse_place_links(html: str) -> list[str]:
    tree = HTMLParser(html)
    links: list[str] = []
    for a in tree.css("a.hfpxzc"):
        href = a.attributes.get("href") or ""
        if "/maps/place/" in href and href not in links:
            links.append(href)
    return links


def _unwrap_google_redirect(href: str) -> str:
    if href.startswith("/url?") or "google.com/url?" in href:
        return parse_qs(urlparse(href).query).get("q", [href])[0]
    return href


def parse_place(html: str, url: str) -> Lead | None:
    tree = HTMLParser(html)
    h1 = tree.css_first("h1.DUwDvf") or tree.css_first("h1")
    name = h1.text(strip=True) if h1 else ""
    if not name:
        return None
    lead = Lead(name=name, sources=["maps"], listing_url=url.split("?")[0])

    summary = tree.css_first("div.F7nice")
    if summary:
        for node in summary.css('span[role="img"]'):
            label = (node.attributes.get("aria-label") or "").lower()
            if "star" in label:
                lead.rating = parse_float(label)
            elif "review" in label:
                lead.reviews = parse_int(label)

    category = tree.css_first("button.DkEaL")
    if category:
        lead.category = category.text(strip=True)

    address = tree.css_first('button[data-item-id="address"]')
    if address:
        lead.address = re.sub(r"^Address:\s*", "", address.attributes.get("aria-label") or "").strip()

    phone = tree.css_first('button[data-item-id^="phone:tel:"]')
    if phone:
        lead.phone = normalize_phone((phone.attributes.get("data-item-id") or "").split("phone:tel:", 1)[-1])

    website = tree.css_first('a[data-item-id="authority"]')
    if website:
        href = _unwrap_google_redirect(website.attributes.get("href") or "")
        if is_social(href):
            lead.socials.append(href)
        elif href.startswith("http"):
            lead.website = href.split("?")[0]  # drop utm tracking params
    return lead


async def _block_heavy_resources(context: BrowserContext) -> None:
    async def handler(route):
        if route.request.resource_type in ("image", "media", "font"):
            await route.abort()
        else:
            await route.continue_()

    await context.route("**/*", handler)


async def _collect_links(page: Page, limit: int) -> list[str]:
    if "/maps/place/" in page.url:  # query matched a single business
        return [page.url]
    await page.wait_for_selector('div[role="feed"]', timeout=20_000)
    feed = page.locator('div[role="feed"]')
    links: list[str] = []
    stale = 0
    while len(links) < limit and stale < MAX_STALE_SCROLLS:
        html = await page.content()
        found = parse_place_links(html)
        stale = stale + 1 if len(found) == len(links) else 0
        links = found
        if END_OF_LIST in html:
            break
        await feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        await polite_sleep(1.5, 2.5)
    return links[:limit]


async def _scrape_place(context: BrowserContext, href: str, sink: list[Lead], sem: asyncio.Semaphore) -> None:
    async with sem:
        page = await context.new_page()
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_selector("h1", timeout=15_000)
            try:  # contact buttons render just after the title
                await page.wait_for_selector('button[data-item-id="address"]', timeout=5_000)
            except PlaywrightError:
                pass
            lead = parse_place(await page.content(), href)
            if lead:
                sink.append(lead)
        except PlaywrightError as exc:
            log.debug("maps: place failed %s: %s", href, str(exc).splitlines()[0])
        finally:
            await page.close()
        await polite_sleep(1.0, 2.5)


async def run(keyword: str, city: str, limit: int, sink: list[Lead], browser: Browser) -> None:
    context = await browser.new_context(**CONTEXT_OPTIONS)
    start = len(sink)
    try:
        await _block_heavy_resources(context)
        page = await context.new_page()
        await page.goto(SEARCH_URL.format(query=quote_plus(f"{keyword} in {city}")),
                        wait_until="domcontentloaded", timeout=60_000)
        if "/sorry/" in page.url:
            log.warning("maps: Google served a CAPTCHA, skipping Maps")
            return
        if "consent.google" in page.url:
            await page.get_by_role("button", name=re.compile(r"Accept all|I agree", re.I)).first.click()
            await page.wait_for_load_state("domcontentloaded")

        links = await _collect_links(page, limit)
        await page.close()
        log.info("maps: found %d places, opening each", len(links))
        sem = asyncio.Semaphore(DETAIL_CONCURRENCY)
        await asyncio.gather(*(_scrape_place(context, href, sink, sem) for href in links))
    except PlaywrightError as exc:
        log.warning("maps: stopped early: %s", str(exc).splitlines()[0])
    finally:
        await context.close()
        log.info("maps: collected %d places", len(sink) - start)
