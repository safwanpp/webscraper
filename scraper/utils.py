import asyncio
import logging
import random
import re
from urllib.parse import urlparse

import phonenumbers

log = logging.getLogger("leads")

REGION = "IN"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

CONTEXT_OPTIONS = {
    "user_agent": USER_AGENT,
    "locale": "en-IN",
    "timezone_id": "Asia/Kolkata",
    "viewport": {"width": 1366, "height": 900},
}

SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
)

# Hosts shared by many unrelated businesses; matching on them proves nothing.
SHARED_HOSTS = {"sites.google.com", "linktr.ee", "g.page", "maps.app.goo.gl", "bit.ly", "wa.me"}


def normalize_phone(raw: str) -> str:
    """Return E.164 phone (e.g. +919876543210) or "" if invalid."""
    if not raw:
        return ""
    try:
        number = phonenumbers.parse(raw, REGION)
    except phonenumbers.NumberParseException:
        return ""
    if not _is_local_valid(number):
        return ""
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def _is_local_valid(number: phonenumbers.PhoneNumber) -> bool:
    # Leads are India-only; foreign numbers on a site are theme demo text.
    return phonenumbers.is_valid_number(number) and phonenumbers.region_code_for_number(number) == REGION


def find_phones(text: str, max_results: int = 5) -> list[str]:
    """Find valid phone numbers in free text."""
    found: list[str] = []
    for match in phonenumbers.PhoneNumberMatcher(text[:200_000], REGION):
        if not _is_local_valid(match.number):
            continue
        e164 = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        if e164 not in found:
            found.append(e164)
        if len(found) >= max_results:
            break
    return found


def host_of(url: str) -> str:
    """Lowercase host without leading www."""
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def host_matches(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def is_social(url: str) -> bool:
    return host_matches(host_of(url), SOCIAL_DOMAINS)


def homepage(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def parse_int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_float(text: str) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(match.group().replace(",", ".")) if match else None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


async def polite_sleep(min_s: float = 1.0, max_s: float = 3.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))
