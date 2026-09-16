"""Merge the same business found by several sources."""

import re

from rapidfuzz import fuzz

from .models import Lead
from .utils import SHARED_HOSTS, host_of

NAME_MATCH = 92
ADDRESS_MATCH = 60
MIN_NAME_LEN = 6


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def same_business(a: Lead, b: Lead) -> bool:
    phones_a = {a.phone, *a.extra_phones} - {""}
    phones_b = {b.phone, *b.extra_phones} - {""}
    if phones_a & phones_b:
        return True

    host_a, host_b = host_of(a.website), host_of(b.website)
    if host_a and host_a == host_b and host_a not in SHARED_HOSTS:
        return True

    name_a, name_b = _norm(a.name), _norm(b.name)
    if min(len(name_a), len(name_b)) < MIN_NAME_LEN:
        return False
    if fuzz.token_set_ratio(name_a, name_b) < NAME_MATCH:
        return False
    if a.address and b.address:
        return fuzz.token_set_ratio(_norm(a.address), _norm(b.address)) >= ADDRESS_MATCH
    # No address to confirm: demand near-identical names.
    return fuzz.ratio(name_a, name_b) >= 90


def merge_into(dst: Lead, src: Lead) -> None:
    for source in src.sources:
        if source not in dst.sources:
            dst.sources.append(source)
    for attr in ("phone", "website", "whatsapp", "address", "category", "listing_url"):
        if not getattr(dst, attr):
            setattr(dst, attr, getattr(src, attr))
    for phone in [src.phone, *src.extra_phones]:
        if phone and phone != dst.phone and phone not in dst.extra_phones:
            dst.extra_phones.append(phone)
    for attr in ("emails", "socials"):
        items = getattr(dst, attr)
        items.extend(x for x in getattr(src, attr) if x not in items)
    if dst.rating is None:
        dst.rating = src.rating
    if src.reviews is not None and (dst.reviews is None or src.reviews > dst.reviews):
        dst.reviews = src.reviews
    for attr in ("https", "mobile_friendly"):
        if getattr(dst, attr) is None:
            setattr(dst, attr, getattr(src, attr))


def dedupe(leads: list[Lead]) -> list[Lead]:
    """Leads earlier in the list win conflicts, so pass the most trusted source first."""
    merged: list[Lead] = []
    for lead in leads:
        for existing in merged:
            if same_business(existing, lead):
                merge_into(existing, lead)
                break
        else:
            merged.append(lead)
    return merged
