#!/usr/bin/env python3
"""Scrape and rank business leads from Google Maps, JustDial and DuckDuckGo.

Setup:
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium

Examples:
    python leads.py "dentists" "Mumbai"
    python leads.py "interior designers" "Pune" --limit 50 --require-phone
    python leads.py "cafes" "Bangalore" --sources maps --no-website-only
"""

import argparse
import asyncio
import logging
import sys
from contextlib import AsyncExitStack

import httpx

from scraper import justdial, maps, search
from scraper.dedupe import dedupe
from scraper.enrich import enrich_all
from scraper.export import write_csv
from scraper.models import Lead
from scraper.score import passes_filters, score
from scraper.utils import USER_AGENT, log, slug

ALL_SOURCES = ("maps", "justdial", "search")  # order = trust order when merging
BROWSER_SOURCES = {"maps", "justdial"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("keyword", help='business type, e.g. "dentists"')
    p.add_argument("city", help='Indian city, e.g. "Mumbai"')
    p.add_argument("--limit", type=int, default=100, help="max leads per source (default 100)")
    p.add_argument("--sources", default=",".join(ALL_SOURCES),
                   help="comma list of maps,justdial,search (default all)")
    p.add_argument("--out", help="CSV path (default leads_<keyword>_<city>.csv)")
    p.add_argument("--require-phone", action="store_true", help="keep only leads with a phone")
    p.add_argument("--require-email", action="store_true", help="keep only leads with an email")
    p.add_argument("--min-rating", type=float, help="keep only leads rated at least this")
    p.add_argument("--min-reviews", type=int, help="keep only leads with at least this many reviews")
    p.add_argument("--no-website-only", action="store_true", help="keep only leads without a website")
    p.add_argument("--headful", action="store_true", help="show the browser window")
    p.add_argument("--concurrency", type=int, default=10, help="parallel website fetches (default 10)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = p.parse_args(argv)

    args.sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = set(args.sources) - set(ALL_SOURCES)
    if unknown:
        p.error(f"unknown source(s): {', '.join(sorted(unknown))}")
    args.sources = [s for s in ALL_SOURCES if s in args.sources]
    args.out = args.out or f"leads_{slug(args.keyword)}_{slug(args.city)}.csv"
    return args


def finalize(leads: list[Lead], args: argparse.Namespace) -> list[Lead]:
    for lead in leads:
        lead.score = score(lead)
    return [
        lead for lead in leads
        if passes_filters(
            lead,
            require_phone=args.require_phone,
            require_email=args.require_email,
            min_rating=args.min_rating,
            min_reviews=args.min_reviews,
            no_website_only=args.no_website_only,
        )
    ]


async def collect(args: argparse.Namespace) -> None:
    sinks: dict[str, list[Lead]] = {source: [] for source in args.sources}
    merged: list[Lead] = []

    def gathered() -> list[Lead]:
        return dedupe([lead for source in args.sources for lead in sinks[source]])

    try:
        async with AsyncExitStack() as stack:
            client = await stack.enter_async_context(httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"},
                follow_redirects=True,
                timeout=15,
            ))
            browser = None
            if BROWSER_SOURCES & set(args.sources):
                from playwright.async_api import async_playwright

                playwright = await stack.enter_async_context(async_playwright())
                # Full Chromium ("new headless"): JustDial blocks the lighter headless shell.
                browser = await playwright.chromium.launch(
                    channel="chromium",
                    headless=not args.headful,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                stack.push_async_callback(browser.close)

            runners = {
                "maps": lambda: maps.run(args.keyword, args.city, args.limit, sinks["maps"], browser),
                "justdial": lambda: justdial.run(args.keyword, args.city, args.limit, sinks["justdial"], browser),
                "search": lambda: search.run(args.keyword, args.city, args.limit, sinks["search"], client),
            }
            results = await asyncio.gather(*(runners[s]() for s in args.sources), return_exceptions=True)
            for source, result in zip(args.sources, results):
                if isinstance(result, Exception):
                    log.error("%s: crashed: %r", source, result)

            merged = gathered()
            log.info("merged %d raw leads into %d unique", sum(map(len, sinks.values())), len(merged))
            write_csv(finalize(merged, args), args.out)  # checkpoint before the slow part

            await enrich_all(merged, client, concurrency=args.concurrency)
            merged = dedupe(merged)  # phones found on websites can reveal more duplicates
    finally:
        leads = finalize(merged or gathered(), args)
        write_csv(leads, args.out)
        log.info("wrote %d leads to %s", len(leads), args.out)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(collect(args))
    except KeyboardInterrupt:
        log.warning("interrupted; partial results saved to %s", args.out)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
