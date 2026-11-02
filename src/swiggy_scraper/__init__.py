"""Scrape Swiggy dishes, restaurants and full menus with Python, through the Scrape.do API."""

from .client import CITIES, ScrapeError, SwiggyScraper
from .parser import (
    DISH_FIELDS,
    RESTAURANT_FIELDS,
    parse_count,
    parse_item,
    parse_listing,
    parse_menu,
    parse_restaurant,
    parse_search_dishes,
    parse_search_restaurants,
    restaurant_id_from_url,
    rupees,
)

__version__ = "0.1.0"

__all__ = [
    "CITIES",
    "DISH_FIELDS",
    "RESTAURANT_FIELDS",
    "ScrapeError",
    "SwiggyScraper",
    "parse_count",
    "parse_item",
    "parse_listing",
    "parse_menu",
    "parse_restaurant",
    "parse_search_dishes",
    "parse_search_restaurants",
    "restaurant_id_from_url",
    "rupees",
    "__version__",
]
