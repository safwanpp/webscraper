"""Lead scoring (contactability-weighted) and filters. Edit WEIGHTS to taste."""

from .models import Lead

WEIGHTS = {
    "phone": 30,
    "email": 30,
    "whatsapp_or_socials": 10,
    "website": 10,
    "good_rating": 10,
    "many_reviews": 10,
}
GOOD_RATING = 4.0
MANY_REVIEWS = 20


def score(lead: Lead) -> int:
    checks = {
        "phone": bool(lead.phone),
        "email": bool(lead.emails),
        "whatsapp_or_socials": bool(lead.whatsapp or lead.socials),
        "website": bool(lead.website),
        "good_rating": lead.rating is not None and lead.rating >= GOOD_RATING,
        "many_reviews": lead.reviews is not None and lead.reviews >= MANY_REVIEWS,
    }
    total = sum(WEIGHTS[name] for name, ok in checks.items() if ok)
    return round(100 * total / sum(WEIGHTS.values()))


def passes_filters(
    lead: Lead,
    *,
    require_phone: bool = False,
    require_email: bool = False,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    no_website_only: bool = False,
) -> bool:
    if require_phone and not lead.phone:
        return False
    if require_email and not lead.emails:
        return False
    if min_rating is not None and (lead.rating is None or lead.rating < min_rating):
        return False
    if min_reviews is not None and (lead.reviews is None or lead.reviews < min_reviews):
        return False
    if no_website_only and lead.website:
        return False
    return True
