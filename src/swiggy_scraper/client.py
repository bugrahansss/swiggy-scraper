"""Fetch Swiggy's JSON APIs through the Scrape.do API.

Swiggy sits behind AWS WAF. A script with a browser user agent gets HTTP 202
with an empty body and ``x-amzn-waf-action: challenge``; with the default
``requests`` user agent it gets a 403 page. Through Scrape.do a plain request
from India (``geoCode=in``) returns the JSON, for 1 credit.

Everything depends on the delivery location (``lat``/``lng`` in the query):
which restaurants deliver, how far they are and how long delivery takes.
Without a location this package uses central Bengaluru.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from .parser import (
    SWIGGY, parse_listing, parse_menu, parse_search_dishes, parse_search_restaurants, restaurant_id_from_url,
)

API_URL = "https://api.scrape.do/"
TOKEN_ENV = "SCRAPEDO_TOKEN"

CITIES = {
    "bengaluru": (12.9715987, 77.5945627),
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6315, 77.2167),
    "gurugram": (28.4595, 77.0266),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
}
DEFAULT_CITY = "bengaluru"


class ScrapeError(RuntimeError):
    """A request that did not return usable data. ``from_target`` is True when the status came from Swiggy."""

    def __init__(self, message: str, status_code: Optional[int] = None, from_target: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.from_target = from_target


class SwiggyScraper:
    """Swiggy search, restaurant lists and full menus, for one delivery location.

    >>> scraper = SwiggyScraper(token="...", city="mumbai")
    >>> dishes = scraper.search_dishes("biryani")
    >>> menu = scraper.get_menu("https://www.swiggy.com/city/bangalore/starbucks-coffee-ashok-nagar-rest124178")
    """

    def __init__(
        self,
        token: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        city: Optional[str] = None,
        timeout: float = 60,
        retries: int = 2,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.token = (token or os.getenv(TOKEN_ENV) or "").strip()
        if not self.token:
            raise ValueError(f"A Scrape.do API token is required (pass token= or set {TOKEN_ENV}).")
        if lat is None or lng is None:
            key = (city or DEFAULT_CITY).strip().lower()
            if key in ("bangalore", "bengaluru"):
                key = "bengaluru"
            if key not in CITIES:
                raise ValueError(f"Unknown city {city!r}. Known: {', '.join(sorted(CITIES))}. Or pass lat and lng.")
            lat, lng = CITIES[key]
        self.lat = float(lat)
        self.lng = float(lng)
        self.timeout = timeout
        self.retries = max(0, retries)
        self.session = session or requests.Session()
        self.credits_used = 0

    # ------------------------------------------------------------ transport

    def fetch_json(self, path: str, **query: Any) -> Dict[str, Any]:
        """GET a Swiggy ``/dapi`` endpoint through Scrape.do and return its ``data`` object."""
        url = f"{SWIGGY}{path}?{urlencode(query)}"
        params = {"token": self.token, "url": url, "geoCode": "in"}
        last: Optional[ScrapeError] = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(1.5 * attempt)
            try:
                response = self.session.get(API_URL, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last = ScrapeError(f"Request failed: {str(exc).replace(self.token, '***')}")
                continue
            from_target = "scrape.do-initial-status-code" in {k.lower() for k in response.headers}
            try:
                self.credits_used += int(response.headers.get("scrape.do-request-cost") or 0)
            except ValueError:
                pass
            if response.status_code == 401 and not from_target:
                raise ScrapeError("Scrape.do rejected the token (HTTP 401).", 401, False)
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if isinstance(body, dict) and body.get("statusCode") == 0 and isinstance(body.get("data"), dict):
                    return body["data"]
                message = (body or {}).get("statusMessage") if isinstance(body, dict) else None
                last = ScrapeError(f"Swiggy returned no data for {url}" + (f": {message}" if message else ""), 200, True)
                if isinstance(body, dict) and body.get("statusCode") not in (None, 0):
                    break
                continue
            last = ScrapeError(f"HTTP {response.status_code} for {url}", response.status_code, from_target)
            if response.status_code not in (429, 500, 502, 503, 504):
                break
        raise last or ScrapeError(f"Request failed: {url}")

    def _search(self, query: str, tab: str) -> Dict[str, Any]:
        if not str(query or "").strip():
            raise ValueError("Search query is empty.")
        return self.fetch_json(
            "/dapi/restaurants/search/v3", lat=self.lat, lng=self.lng, str=query.strip(),
            trackingId="undefined", submitAction="ENTER", selectedPLTab=tab,
        )

    # ------------------------------------------------------------- scraping

    def search_dishes(self, query: str) -> List[Dict[str, Any]]:
        """Dishes matching ``query`` from restaurants that deliver here: price, veg, rating, variants,
        restaurant. One request (about 50 restaurants, every matching dish of each)."""
        return parse_search_dishes(self._search(query, "DISH"))

    def search_restaurants(self, query: str) -> List[Dict[str, Any]]:
        """Restaurants matching ``query`` that deliver here. One request, ~100 restaurants."""
        return parse_search_restaurants(self._search(query, "RESTAURANT"))

    def get_restaurants(self) -> List[Dict[str, Any]]:
        """The restaurants on Swiggy's home page for this location (top brands and the main grid)."""
        return parse_listing(self.fetch_json(
            "/dapi/restaurants/list/v5", lat=self.lat, lng=self.lng,
            **{"is-seo-homepage-enabled": "true", "page_type": "DESKTOP_WEB_LISTING"},
        ))

    def get_menu(self, url_or_id: Any) -> Dict[str, Any]:
        """Full menu of a restaurant: ``{"restaurant": {...}, "items": [...]}``. The restaurant row includes
        the FSSAI licence, address, and whether it delivers to this location."""
        restaurant_id = restaurant_id_from_url(str(url_or_id))
        if not restaurant_id:
            raise ValueError("Expected a Swiggy restaurant URL (…-rest<ID> or /restaurants/…-<ID>) or a restaurant id.")
        menu = parse_menu(self.fetch_json(
            "/dapi/menu/pl", **{"page-type": "REGULAR_MENU", "complete-menu": "true"},
            lat=self.lat, lng=self.lng, restaurantId=restaurant_id,
        ))
        if not menu["restaurant"].get("restaurant_id"):
            raise ScrapeError(f"No restaurant {restaurant_id} on Swiggy.", 200, True)
        return menu
