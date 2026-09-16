# Web Scraper

Lead generation tool that scrapes business data from Google Maps, JustDial, and DuckDuckGo, then enriches with website crawling.

## Features

- **Multi-source scraping**: Google Maps (Playwright), JustDial (Playwright), DuckDuckGo search (HTTP)
- **Website enrichment**: Crawls business websites for emails, phones, WhatsApp, social links
- **Deduplication**: Fuzzy matching on business names, phone numbers, and website domains
- **Scoring**: Contactability-weighted scoring (phone 30%, email 30%, website 10%, rating 10%, reviews 10%, socials 10%)
- **Filtering**: Filter by phone, email, rating, reviews, no-website
- **Atomic CSV export**: Crash-safe CSV with BOM for Excel compatibility

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Basic search
python leads.py "dentists" "Mumbai"

# With filters
python leads.py "interior designers" "Pune" --limit 50 --require-phone

# Specific sources only
python leads.py "cafes" "Bangalore" --sources maps --no-website-only

# Custom output path
python leads.py "gyms" "Delhi" --out gyms_delhi.csv

# Verbose logging
python leads.py "restaurants" "Chennai" -v
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--limit N` | Max leads per source (default: 100) |
| `--sources` | Comma-separated: maps, justdial, search (default: all) |
| `--out PATH` | CSV output path (default: `leads_<keyword>_<city>.csv`) |
| `--require-phone` | Keep only leads with phone |
| `--require-email` | Keep only leads with email |
| `--min-rating N` | Minimum rating filter |
| `--min-reviews N` | Minimum reviews filter |
| `--no-website-only` | Keep only leads without website |
| `--headful` | Show browser window |
| `--concurrency N` | Parallel website fetches (default: 10) |
| `-v, --verbose` | Debug logging |

## Architecture

```
leads.py              # CLI entry point, orchestration
scraper/
  models.py           # Lead dataclass
  maps.py             # Google Maps scraper (Playwright)
  justdial.py         # JustDial scraper (Playwright)
  search.py           # DuckDuckGo search scraper (HTTP)
  enrich.py           # Website crawler (emails, phones, socials)
  dedupe.py           # Fuzzy deduplication
  score.py            # Lead scoring & filters
  export.py           # CSV writer
  utils.py            # Phone normalization, helpers
tests/
  test_*.py           # Unit tests
```

## Tests

```bash
pytest
```

## How It Works

1. **Scrape**: Collects leads from selected sources in parallel
2. **Dedup**: Matches same business across sources via phone, domain, or fuzzy name+address
3. **Checkpoint**: Writes initial CSV (partial results safe on crash)
4. **Enrich**: Crawls each lead's website for emails, phones, WhatsApp, socials
5. **Re-dedup**: Catches duplicates revealed by newly found phone numbers
6. **Score & Filter**: Applies scoring and CLI filters
7. **Export**: Final sorted CSV with BOM for Excel

## Notes

- India-only phone validation (E.164 format)
- Polite crawling with random delays
- JustDial hides phones behind login; enrichment fills gaps
- Blocks 60+ directory/aggregator domains in search results
