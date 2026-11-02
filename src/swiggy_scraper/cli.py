"""Command line entry point: ``swiggy-scraper dishes|restaurants|nearby|menu``."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import List, Optional

from . import __version__
from .client import CITIES, TOKEN_ENV, ScrapeError, SwiggyScraper
from .parser import DISH_FIELDS, RESTAURANT_FIELDS

MENU_FIELDS = DISH_FIELDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swiggy-scraper",
        description="Scrape Swiggy dishes, restaurants and full menus (prices, ratings, delivery time) into JSON or CSV.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    dishes = sub.add_parser("dishes", help="Search dishes: every matching dish with price and restaurant")
    dishes.add_argument("query", help='What to search, e.g. "biryani"')
    rest = sub.add_parser("restaurants", help="Search restaurants that deliver to the location")
    rest.add_argument("query", help='What to search, e.g. "pizza"')
    sub.add_parser("nearby", help="Restaurants on the Swiggy home page for the location")
    menu = sub.add_parser("menu", help="Full menus: every dish with price, variants, veg, stock, rating")
    menu.add_argument("urls", nargs="*", help="Swiggy restaurant URLs or ids")
    menu.add_argument("-i", "--input", help="Text file with one URL per line, or a CSV with a 'url' column")
    menu.add_argument("--limit", type=int, default=0, help="Stop after this many restaurants (0 = all)")

    for p in (dishes, rest, sub.choices["nearby"], menu):
        p.add_argument("-t", "--token", help=f"Scrape.do API token (default: ${TOKEN_ENV})")
        p.add_argument("--city", choices=sorted(CITIES), help="Delivery location preset (default: bengaluru)")
        p.add_argument("--lat", type=float, help="Delivery latitude (with --lng)")
        p.add_argument("--lng", type=float, help="Delivery longitude (with --lat)")
        p.add_argument("-f", "--format", choices=("json", "csv"), default="json")
        p.add_argument("-o", "--output", help="Write to this file instead of stdout")
    return parser


def _read_urls(args: argparse.Namespace) -> List[str]:
    urls = list(args.urls)
    if args.input:
        with open(args.input, encoding="utf-8", newline="") as handle:
            if args.input.endswith(".csv"):
                urls.extend(row["url"] for row in csv.DictReader(handle) if row.get("url"))
            else:
                urls.extend(line.strip() for line in handle if line.strip() and not line.startswith("#"))
    return urls[: args.limit] if args.limit else urls


def _write(rows: List[dict], fields: List[str], fmt: str, stream) -> None:
    if fmt == "csv":
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    else:
        json.dump(rows, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.lat is None) != (args.lng is None):
        print("Pass both --lat and --lng.", file=sys.stderr)
        return 2
    try:
        scraper = SwiggyScraper(token=args.token, lat=args.lat, lng=args.lng, city=args.city)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    failures = 0
    rows: List[dict] = []
    try:
        if args.command == "dishes":
            fields, rows = DISH_FIELDS + ["restaurant_rating", "delivery_time_min", "restaurant_promoted"], scraper.search_dishes(args.query)
        elif args.command == "restaurants":
            fields, rows = RESTAURANT_FIELDS, scraper.search_restaurants(args.query)
        elif args.command == "nearby":
            fields, rows = RESTAURANT_FIELDS, scraper.get_restaurants()
        else:
            fields = MENU_FIELDS
            urls = _read_urls(args)
            if not urls:
                print("No URLs given. Pass restaurant URLs or --input FILE.", file=sys.stderr)
                return 2
            for url in urls:
                try:
                    menu = scraper.get_menu(url)
                except (ScrapeError, ValueError) as exc:
                    failures += 1
                    print(f"fail  {url}: {exc}", file=sys.stderr)
                    continue
                rows.extend(menu["items"])
                r = menu["restaurant"]
                print(f"ok    {r['name']} ({r['area']}): {len(menu['items'])} dishes, FSSAI {r['fssai_license']}", file=sys.stderr)
    except (ScrapeError, ValueError) as exc:
        print(f"fail  {exc}", file=sys.stderr)
        return 1

    print(f"{len(rows)} rows, {scraper.credits_used} credits", file=sys.stderr)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="" if args.format == "csv" else None) as handle:
            _write(rows, fields, args.format, handle)
        print(f"Saved {len(rows)} rows to {args.output}", file=sys.stderr)
    else:
        _write(rows, fields, args.format, sys.stdout)
    return 1 if failures and not rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
