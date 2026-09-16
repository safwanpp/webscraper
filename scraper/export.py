import csv
import os
from pathlib import Path

from .models import Lead

COLUMNS = [
    "score", "name", "phone", "extra_phones", "emails", "whatsapp", "website",
    "socials", "rating", "reviews", "category", "address", "https",
    "mobile_friendly", "sources", "listing_url",
]


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def write_csv(leads: list[Lead], path: str | Path) -> None:
    """Write leads sorted by score. Atomic, so a crash never leaves a half file."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    rows = sorted(leads, key=lambda lead: lead.score, reverse=True)
    with tmp.open("w", newline="", encoding="utf-8-sig") as fh:  # BOM: Excel-friendly
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for lead in rows:
            writer.writerow([_cell(getattr(lead, col)) for col in COLUMNS])
    os.replace(tmp, path)
