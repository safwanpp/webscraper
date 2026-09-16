"""Visit each lead's website and extract emails, phones, WhatsApp, socials."""

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin

import httpx
from selectolax.parser import HTMLParser

from .models import Lead
from .utils import find_phones, host_of, is_social, log, normalize_phone

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BAD_EMAIL_PARTS = (
    "example.", "sentry", "wixpress", "domain.com", "email.com", "yourname",
    "yoursite", "@2x", "godaddy", "noreply", "no-reply", "donotreply", "envato",
    "themeforest", "wordpress.", "wix.com", "squarespace",
)
BAD_EMAIL_TLDS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
CONTACT_HINTS = ("contact", "about", "reach", "location", "find-us")
WHATSAPP_RE = re.compile(r"(?:wa\.me/|phone=)(\+?\d{10,15})")
MAX_EXTRA_PAGES = 2


@dataclass
class SiteInfo:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    whatsapp: str = ""
    socials: list[str] = field(default_factory=list)
    contact_links: list[str] = field(default_factory=list)
    mobile_friendly: bool = False
    site_name: str = ""


def decode_cfemail(encoded: str) -> str:
    """Decode Cloudflare email obfuscation (data-cfemail hex)."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except ValueError:
        return ""


def clean_email(raw: str) -> str:
    email = unquote(raw).split("?")[0].strip().strip(".").lower()
    if not EMAIL_RE.fullmatch(email):
        return ""
    if any(part in email for part in BAD_EMAIL_PARTS) or email.endswith(BAD_EMAIL_TLDS):
        return ""
    return email


def _add(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def parse_page(html: str, base_url: str) -> SiteInfo:
    info = SiteInfo()
    tree = HTMLParser(html)
    base_host = host_of(base_url)

    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            _add(info.emails, clean_email(href[7:]))
        elif low.startswith("tel:"):
            _add(info.phones, normalize_phone(unquote(href[4:])))
        elif "wa.me/" in low or "whatsapp.com" in low:
            match = WHATSAPP_RE.search(href)
            if match and not info.whatsapp:
                digits = match.group(1)
                info.whatsapp = normalize_phone(digits if digits.startswith("+") or len(digits) == 10 else "+" + digits)
        elif "/cdn-cgi/l/email-protection#" in low:
            _add(info.emails, clean_email(decode_cfemail(href.split("#", 1)[1])))
        elif is_social(href):
            _add(info.socials, href.split("?")[0].rstrip("/"))
        elif any(hint in low for hint in CONTACT_HINTS):
            absolute = urljoin(base_url, href).split("#")[0]
            if host_of(absolute) == base_host:
                _add(info.contact_links, absolute)

    for node in tree.css("[data-cfemail]"):
        _add(info.emails, clean_email(decode_cfemail(node.attributes.get("data-cfemail") or "")))

    info.mobile_friendly = tree.css_first('meta[name="viewport"]') is not None
    og_name = tree.css_first('meta[property="og:site_name"]')
    if og_name:
        info.site_name = (og_name.attributes.get("content") or "").strip()

    tree.strip_tags(["script", "style", "noscript", "svg"])
    text = tree.body.text(separator=" ") if tree.body else ""
    for raw in EMAIL_RE.findall(text):
        _add(info.emails, clean_email(raw))
    for phone in find_phones(text):
        _add(info.phones, phone)

    # Emails on the business's own domain first.
    info.emails.sort(key=lambda e: 0 if base_host and e.endswith("@" + base_host) else 1)
    return info


async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        resp = await client.get(url)
    except httpx.HTTPError as exc:
        log.debug("enrich: %s failed: %s", url, exc)
        return None
    if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", ""):
        return None
    return resp


async def enrich_lead(lead: Lead, client: httpx.AsyncClient) -> None:
    if not lead.website:
        return
    resp = await _fetch(client, lead.website)
    if resp is None:
        return
    final_url = str(resp.url)
    lead.https = final_url.startswith("https://")
    info = parse_page(resp.text, final_url)
    lead.mobile_friendly = info.mobile_friendly

    for link in info.contact_links[:MAX_EXTRA_PAGES]:
        extra_resp = await _fetch(client, link)
        if extra_resp is None:
            continue
        extra = parse_page(extra_resp.text, final_url)
        for email in extra.emails:
            _add(info.emails, email)
        for phone in extra.phones:
            _add(info.phones, phone)
        for social in extra.socials:
            _add(info.socials, social)
        info.whatsapp = info.whatsapp or extra.whatsapp

    for email in info.emails:
        _add(lead.emails, email)
    for social in info.socials:
        _add(lead.socials, social)
    lead.whatsapp = lead.whatsapp or info.whatsapp
    for phone in info.phones:
        if not lead.phone:
            lead.phone = phone
        elif phone != lead.phone:
            _add(lead.extra_phones, phone)
    if lead.sources == ["search"] and info.site_name:
        lead.name = info.site_name


async def enrich_all(leads: list[Lead], client: httpx.AsyncClient, concurrency: int = 10) -> None:
    targets = [lead for lead in leads if lead.website]
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def worker(lead: Lead) -> None:
        nonlocal done
        async with sem:
            try:
                await enrich_lead(lead, client)
            except Exception as exc:  # one bad site must not stop the run
                log.debug("enrich: %s crashed: %s", lead.website, exc)
        done += 1
        if done % 10 == 0 or done == len(targets):
            log.info("enrich: %d/%d websites", done, len(targets))

    await asyncio.gather(*(worker(lead) for lead in targets))
