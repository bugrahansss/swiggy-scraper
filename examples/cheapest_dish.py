"""Cheapest delivered biryani in two cities, from one search request each.

    export SCRAPEDO_TOKEN=your_token
    python examples/cheapest_dish.py biryani
"""
import sys

from swiggy_scraper import SwiggyScraper

query = sys.argv[1] if len(sys.argv) > 1 else "biryani"
for city in ("bengaluru", "mumbai"):
    scraper = SwiggyScraper(city=city)
    # search also returns sides (raita, pappadam): keep dishes that carry the query in their name
    dishes = [d for d in scraper.search_dishes(query) if d["in_stock"] and d["price_inr"] and query.lower() in d["name"].lower()]
    restaurants = {d["restaurant_id"] for d in dishes}
    cheapest = sorted(dishes, key=lambda d: d["price_inr"])[:3]
    print(f"\n{city}: {len(dishes)} dishes from {len(restaurants)} restaurants")
    for d in cheapest:
        print(f"  Rs {d['price_inr']:>6}  {d['name']}  ({d['restaurant_name']}, {d['delivery_time_min']} min)")
