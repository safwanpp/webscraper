"""DuckDuckGo (lite endpoint) search -> business websites."""

import re

import httpx
from selectolax.parser import HTMLParser

from .models import Lead
from .utils import homepage, host_matches, host_of, log, polite_sleep

LITE_URL = "https://lite.duckduckgo.com/lite/"
MAX_PAGES_PER_QUERY = 5

# Directories, marketplaces, media and socials: not the business's own site.
BLOCKED_DOMAINS = {
    "justdial.com", "justdial.in", "practo.com", "sulekha.com", "indiamart.com",
    "tradeindia.com", "yelp.com", "tripadvisor.com", "tripadvisor.in", "zomato.com",
    "swiggy.com", "magicpin.in", "lybrate.com", "whatclinic.com", "google.com",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "wikipedia.org", "quora.com", "reddit.com", "medium.com",
    "amazon.in", "amazon.com", "flipkart.com", "urbancompany.com", "housing.com",
    "99acres.com", "magicbricks.com", "nobroker.in", "glassdoor.com", "glassdoor.co.in",
    "naukri.com", "indeed.com", "crunchbase.com", "zaubacorp.com", "tofler.in",
    "credihealth.com", "clinicspots.com", "bestinthecity.in", "threebestrated.in",
    "yellowpages.in", "asklaila.com", "grotal.com", "nearbuy.com", "booking.com",
    "makemytrip.com", "goibibo.com", "mouthshut.com", "pinterest.com", "apollo247.com",
    "1mg.com", "docprime.com", "bajajfinservhealth.in", "hindustantimes.com",
    "indiatimes.com", "ndtv.com", "wanderlog.com", "top10place.com", "joonsquare.com",
}

LISTICLE_RE = re.compile(r"\b(top|best)\s+\d+\b|\blist of\b", re.I)
# Directory/aggregator-style hostnames, e.g. bestmumbai.in, top10dentists.com.
HOST_NOISE_RE = re.compile(r"best|top\d|directory|listing|nearme|near-me")
TITLE_NOISE_RE = re.compile(
    r"\b(best|top|near me|reviews?|contact us|home|official (web)?site|welcome)\b", re.I
)


def parse_results(html: str) -> tuple[list[tuple[str, str]], dict | None]:
    """Return ([(title, url)], next-page form data or None)."""
    tree = HTMLParser(html)
    results = [
        (a.text(strip=True), a.attributes.get("href") or "")
        for a in tree.css("a.result-link")
    ]
    next_form = None
    for form in tree.css("form"):
        submit = form.css_first('input[type="submit"]')
        if submit and "next" in (submit.attributes.get("value") or "").lower():
            next_form = {
                inp.attributes["name"]: inp.attributes.get("value") or ""
                for inp in form.css('input[type="hidden"]')
                if inp.attributes.get("name")
            }
            break
    return results, next_form


def is_blocked(url: str, title: str = "") -> bool:
    if not url.startswith("http"):
        return True
    host = host_of(url)
    if host_matches(host, BLOCKED_DOMAINS) or HOST_NOISE_RE.search(host):
        return True
    return bool(LISTICLE_RE.search(title))


def clean_title(title: str, city: str) -> str:
    """Pick the segment of a page title most likely to be the business name."""
    parts = [p.strip() for p in re.split(r"\s+[|\-–—:]\s+", title) if p.strip()]
    if not parts:
        return title.strip()
    good = [
        p for p in parts
        if not TITLE_NOISE_RE.search(p) and city.lower() not in p.lower()
    ]
    return (good[0] if good else parts[0])[:120]


async def run(keyword: str, city: str, limit: int, sink: list[Lead], client: httpx.AsyncClient) -> None:
    queries = [
        f"{keyword} in {city}",
        f"{keyword} {city} contact",
        f"{keyword} {city} phone email",
    ]
    seen_hosts: set[str] = set()
    added = 0
    try:
        for query in queries:
            data: dict | None = {"q": query, "kl": "in-en"}
            pages = 0
            while data and pages < MAX_PAGES_PER_QUERY and added < limit:
                resp = await client.post(LITE_URL, data=data)
                if resp.status_code != 200 or "anomaly" in resp.text[:5000]:
                    log.warning("search: DuckDuckGo blocked request (HTTP %s), stopping", resp.status_code)
                    return
                results, data = parse_results(resp.text)
                if not results:
                    break
                for title, url in results:
                    host = host_of(url)
                    if is_blocked(url, title) or host in seen_hosts:
                        continue
                    seen_hosts.add(host)
                    sink.append(Lead(
                        name=clean_title(title, city),
                        sources=["search"],
                        website=homepage(url),
                        listing_url=url,
                    ))
                    added += 1
                    if added >= limit:
                        break
                pages += 1
                await polite_sleep(2, 4)
    except httpx.HTTPError as exc:
        log.warning("search: request failed: %s", exc)
    finally:
        log.info("search: collected %d websites", added)
