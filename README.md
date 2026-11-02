# swiggy-scraper

[![PyPI](https://img.shields.io/pypi/v/swiggy-scraper)](https://pypi.org/project/swiggy-scraper/)
[![Python](https://img.shields.io/pypi/pyversions/swiggy-scraper)](https://pypi.org/project/swiggy-scraper/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Python scraper for [Swiggy](https://www.swiggy.com), India's food delivery app. Three jobs:

- **Dish search:** search a dish ("biryani") and get every matching dish from the restaurants that deliver to your location: price, veg/non-veg, bestseller flag, rating, rating count, every variant price, and the restaurant with its delivery time. One request, ~50 restaurants.
- **Restaurant search and nearby list:** name, area, cuisines, rating, rating count, cost for two, delivery time, distance, open/serviceable, and whether the listing is a paid (promoted) placement.
- **Full menus:** every dish of a restaurant with price, variants, veg flag, stock and rating, plus the restaurant's **FSSAI licence** and full address.

Output as Python dicts, JSON or CSV. One dependency (`requests`), no browser.

```bash
pip install swiggy-scraper
```

## Why a plain request fails

Swiggy sits behind AWS WAF on CloudFront. A script gets no data:

| Request | Result |
| --- | --- |
| `requests` with a Chrome user agent | HTTP 202, empty body, `x-amzn-waf-action: challenge` |
| `requests` with its default user agent | HTTP 403, an error page |
| Through Scrape.do (`geoCode=in`) | 200 in ~3 s, the JSON, every try |

Requests go through the [Scrape.do](https://scrape.do/?utm_source=github&utm_medium=readme&utm_campaign=swiggy-scraper) API from India. Each request costs 1 credit; the free plan includes 1,000 credits a month.

## Quick start

```python
from swiggy_scraper import SwiggyScraper

scraper = SwiggyScraper(token="YOUR_SCRAPEDO_TOKEN", city="mumbai")  # or lat=..., lng=...

dishes = scraper.search_dishes("biryani")          # 1 request
for d in sorted(dishes, key=lambda d: d["price_inr"])[:3]:
    print(d["price_inr"], d["name"], d["restaurant_name"], d["delivery_time_min"])

menu = scraper.get_menu("https://www.swiggy.com/city/bangalore/starbucks-coffee-ashok-nagar-rest124178")
print(menu["restaurant"]["fssai_license"], len(menu["items"]))
```

### Command line

```bash
export SCRAPEDO_TOKEN=your_token

# every biryani on Swiggy for a Mumbai address
swiggy-scraper dishes biryani --city mumbai -f csv -o swiggy-biryani.csv

# pizza places that deliver to central Bengaluru
swiggy-scraper restaurants pizza -f csv -o swiggy-pizza.csv

# restaurants on the home page for any address
swiggy-scraper nearby --lat 12.9352 --lng 77.6245 -f csv -o swiggy-nearby.csv

# full menus of those restaurants
swiggy-scraper menu -i swiggy-nearby.csv --limit 5 -f csv -o swiggy-menus.csv
```

City presets: `bengaluru` (default), `chennai`, `delhi`, `gurugram`, `hyderabad`, `kolkata`, `mumbai`, `pune`.

### Output

Dish row (from the fictional test data in [`tests/fixtures`](tests/fixtures/menu.json)):

```json
{"item_id": "9001", "name": "Paneer Dum Biryani", "category": "Biryani", "price_inr": 249, "is_veg": true,
 "in_stock": true, "bestseller": true, "rating": 4.4, "rating_count": 210,
 "variant_prices_inr": "Half 249; Full 389", "restaurant_id": "5001", "restaurant_name": "Example Biryani House"}
```

Restaurant columns: `restaurant_id, name, area, locality, cuisines, rating, rating_count, cost_for_two_inr, delivery_time_min, distance_km, serviceable, is_open, promoted, veg_only, url` (menus add `fssai_license` and `address`).

## How it works

**The page is a shell.** A restaurant page (`/city/bangalore/…-rest124178`) is 78 KB of HTML with no menu in it. The browser fills it from JSON endpoints under `/dapi`, and this package calls those directly:

| Data | Endpoint |
| --- | --- |
| Dish / restaurant search | `/dapi/restaurants/search/v3?lat&lng&str=biryani&selectedPLTab=DISH` (or `RESTAURANT`) |
| Home page restaurants | `/dapi/restaurants/list/v5?lat&lng` |
| Full menu | `/dapi/menu/pl?page-type=REGULAR_MENU&complete-menu=true&lat&lng&restaurantId=…` |

Every response is a list of widget cards with an `@type`; the parsers keep the restaurant, dish and licence cards and skip banners, filters and SEO blocks.

**Money is in paise.** `"price": 42000` is Rs 420. Some dishes have no `price`, only `defaultPrice`. Variant prices come either as absolute prices (`variantsV2.pricingModels`) or as a surcharge on the base price (`variants`); both are turned into rupees.

**The menu repeats itself.** The "Recommended" section lists dishes that also appear in their own sections: Starbucks in Bengaluru has 168 dish cards and 148 dishes. Each dish is kept once.

**Location decides the restaurants.** `lat`/`lng` decide which restaurants deliver, how far they are and how long delivery takes. The same "biryani" search returned 50 restaurants in Bengaluru and 50 in Mumbai with none in common. A menu still loads from a far-away location, with `serviceable: false`.

**Some results are ads.** Search mixes in paid placements; they carry `promoted: true` so you can drop them or keep them.

## Responsible use

The package calls the JSON endpoints Swiggy's own web pages use for search, the home page and menus. Swiggy's robots.txt allows these paths and disallows account, cart, checkout, order tracking and payment pages, which this package never touches. It collects restaurant and menu data, not personal data. Read Swiggy's terms for your use case and keep request rates modest.

## License

MIT. Not affiliated with Swiggy.

---

Built with [Scrape.do](https://scrape.do/?utm_source=github&utm_medium=readme&utm_campaign=swiggy-scraper). [Get 1000 free credits](https://dashboard.scrape.do/sign-up?utm_source=github&utm_medium=readme&utm_campaign=swiggy-scraper).
