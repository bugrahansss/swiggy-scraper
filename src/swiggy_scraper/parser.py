"""Turn Swiggy's JSON API responses into flat rows.

Swiggy's web pages are empty shells; the data comes from JSON endpoints under
``/dapi``. Every response wraps its content in ``data.cards``: a list of
widget cards, each with an ``@type``. The parsers below pick the cards they
need and ignore the rest (filters, banners, footers, SEO blocks).

Money is in paise: ``42000`` means Rs 420.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

SWIGGY = "https://www.swiggy.com"
IMAGE_CDN = "https://media-assets.swiggy.com/swiggy/image/upload/"

RESTAURANT_FIELDS = [
    "restaurant_id", "name", "area", "locality", "cuisines", "rating", "rating_count", "cost_for_two_inr",
    "delivery_time_min", "distance_km", "serviceable", "is_open", "promoted", "veg_only", "url",
]
DISH_FIELDS = [
    "item_id", "name", "category", "price_inr", "is_veg", "in_stock", "bestseller", "rating", "rating_count",
    "variant_prices_inr", "restaurant_id", "restaurant_name", "description",
]


def _cards(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((data or {}).get("cards") or [])


def _card(wrapper: Dict[str, Any]) -> Dict[str, Any]:
    return ((wrapper or {}).get("card") or {}).get("card") or {}


def card_type(card: Dict[str, Any]) -> str:
    """``type.googleapis.com/swiggy.presentation.food.v2.Restaurant`` -> ``Restaurant``."""
    return str(card.get("@type") or "").rsplit(".", 1)[-1]


def rupees(paise: Any) -> Optional[float]:
    """42000 -> 420, 12950 -> 129.5. Swiggy sends money in paise."""
    try:
        value = int(float(paise)) / 100
    except (TypeError, ValueError):
        return None
    return int(value) if value == int(value) else value


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cost_for_two(info: Dict[str, Any]) -> Optional[float]:
    """Menu and search send ``costForTwo`` in paise ("40000"); the home list sends "₹400 for two"."""
    raw = info.get("costForTwo")
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
        return rupees(raw)
    match = re.search(r"([\d,]+)", str(raw or info.get("costForTwoMessage") or ""))
    return int(match.group(1).replace(",", "")) if match else None


def parse_count(text: Any) -> Optional[int]:
    """'2.6K+ ratings' -> 2600, '153 ratings' -> 153, '1.2L' -> 120000."""
    match = re.search(r"([\d.,]+)\s*([kKlL]?)", str(text or ""))
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(round(number * {"k": 1_000, "l": 100_000}.get(match.group(2).lower(), 1)))


def restaurant_id_from_url(url: str) -> Optional[str]:
    """Restaurant id from a Swiggy restaurant URL.

    ``/city/bangalore/starbucks-coffee-ashok-nagar-rest124178`` -> ``124178``
    ``/restaurants/starbucks-coffee-ashok-nagar-bangalore-124178`` -> ``124178``
    """
    text = str(url or "").strip().split("?")[0].split("#")[0].rstrip("/")
    if text.isdigit():
        return text
    match = re.search(r"-rest(\d+)$", text) or re.search(r"/restaurants/[^/]*?-(\d+)$", text)
    return match.group(1) if match else None


def restaurant_url(info: Dict[str, Any]) -> Optional[str]:
    slugs = info.get("slugs") or {}
    rid = info.get("id")
    if rid and slugs.get("city") and slugs.get("restaurant"):
        return f"{SWIGGY}/city/{slugs['city']}/{slugs['restaurant']}-rest{rid}"
    return f"{SWIGGY}/restaurants/{rid}" if rid else None


def parse_restaurant(info: Dict[str, Any], url: Optional[str] = None) -> Dict[str, Any]:
    """One restaurant ``info`` object (home list, search or menu) -> flat row."""
    sla = info.get("sla") or {}
    availability = info.get("availability") or {}
    distance = sla.get("lastMileTravel")
    if distance is None:
        distance = _float(re.sub(r"[^\d.]", "", str(sla.get("lastMileTravelString") or "")) or None)
    serviceability = sla.get("serviceability")
    return {
        "restaurant_id": str(info.get("id") or "") or None,
        "name": info.get("name"),
        "area": info.get("areaName"),
        "locality": info.get("locality"),
        "cuisines": ", ".join(info.get("cuisines") or []),
        "rating": _float(info.get("avgRatingString") or info.get("avgRating")),
        "rating_count": info.get("totalRatings") or parse_count(info.get("totalRatingsString")),
        "cost_for_two_inr": _cost_for_two(info),
        "delivery_time_min": sla.get("deliveryTime"),
        "distance_km": _float(distance),
        "serviceable": (serviceability == "SERVICEABLE") if serviceability else None,
        "is_open": bool(info["isOpen"]) if "isOpen" in info else availability.get("opened"),
        "promoted": bool(info.get("promoted")),
        "veg_only": bool(info.get("veg")),
        "url": url or restaurant_url(info),
    }


def _variant_prices(item: Dict[str, Any], base: Optional[float]) -> List[Dict[str, Any]]:
    """Every price a dish can have. ``variantsV2.pricingModels`` carry absolute prices; the older
    ``variants`` carry a surcharge on top of the base price."""
    out: List[Dict[str, Any]] = []
    v2 = item.get("variantsV2") or {}
    names = {
        (str(g.get("groupId")), str(v.get("id"))): v.get("name")
        for g in v2.get("variantGroups") or [] for v in g.get("variations") or []
    }
    for model in v2.get("pricingModels") or []:
        label = " / ".join(
            str(names.get((str(v.get("groupId")), str(v.get("variationId"))), "")).strip()
            for v in model.get("variations") or []
        )
        out.append({"variant": label, "price_inr": rupees(model.get("price"))})
    if out:
        return out
    for group in (item.get("variants") or {}).get("variantGroups") or []:
        for variation in group.get("variations") or []:
            extra = rupees(variation.get("price")) or 0
            out.append({
                "variant": f"{group.get('name', '').strip()}: {str(variation.get('name', '')).strip()}",
                "price_inr": (base or 0) + extra if base is not None else None,
            })
    return out


def parse_item(item: Dict[str, Any], restaurant: Optional[Dict[str, Any]] = None,
               category: Optional[str] = None) -> Dict[str, Any]:
    """One dish ``info`` object -> flat row. ``price`` is missing on some items; ``defaultPrice`` is used then."""
    price = rupees(item.get("price") if item.get("price") is not None else item.get("defaultPrice"))
    rating = ((item.get("ratings") or {}).get("aggregatedRating") or {})
    ribbon = (item.get("ribbon") or {}).get("text") or ""
    variants = _variant_prices(item, price)
    restaurant = restaurant or {}
    return {
        "item_id": str(item.get("id") or "") or None,
        "name": (item.get("name") or "").strip(),
        "category": item.get("category") or category,
        "price_inr": price,
        "is_veg": bool(item.get("isVeg")),
        "in_stock": bool(item.get("inStock", 1)),
        "bestseller": ribbon.strip().lower() == "bestseller",
        "rating": _float(rating.get("rating")),
        "rating_count": parse_count(rating.get("ratingCountV2") or rating.get("ratingCount")),
        "variant_prices_inr": "; ".join(f"{v['variant']} {v['price_inr']}" for v in variants) if variants else "",
        "variants": variants,
        "restaurant_id": restaurant.get("restaurant_id"),
        "restaurant_name": restaurant.get("name"),
        "description": (item.get("description") or "").strip(),
        "image": IMAGE_CDN + item["imageId"] if item.get("imageId") else None,
    }


def _menu_categories(cards: Iterable[Dict[str, Any]]):
    """Yield (category title, item info) for every dish card in a menu, nested categories included."""
    for wrapper in cards:
        card = _card(wrapper)
        title = card.get("title") or ""
        for item_card in card.get("itemCards") or []:
            yield title, ((item_card.get("card") or {}).get("info") or {})
        for sub in card.get("categories") or []:
            for item_card in sub.get("itemCards") or []:
                yield f"{title} / {sub.get('title', '')}".strip(" /"), ((item_card.get("card") or {}).get("info") or {})


def parse_menu(data: Dict[str, Any]) -> Dict[str, Any]:
    """``/dapi/menu/pl`` response -> restaurant row (with FSSAI licence and address) and its dishes.

    The "Recommended" section repeats dishes from other sections; each dish is kept once, with
    the category Swiggy assigns to it."""
    restaurant: Dict[str, Any] = {}
    regular: List[Dict[str, Any]] = []
    for wrapper in _cards(data):
        card = _card(wrapper)
        if card_type(card) == "Restaurant" and card.get("info"):
            restaurant = parse_restaurant(card["info"])
            restaurant["address"] = None
        grouped = (wrapper.get("groupedCard") or {}).get("cardGroupMap") or {}
        if grouped.get("REGULAR"):
            regular = grouped["REGULAR"].get("cards") or []
    for wrapper in regular:
        card = _card(wrapper)
        kind = card_type(card)
        if kind == "RestaurantLicenseInfo":
            text = " ".join(card.get("text") or [])
            match = re.search(r"(\d{10,})", text)
            restaurant["fssai_license"] = match.group(1) if match else (text or None)
        elif kind == "RestaurantAddress":
            restaurant["address"] = card.get("completeAddress")
    items: Dict[str, Dict[str, Any]] = {}
    item_cards = 0
    for category, info in _menu_categories(regular):
        if not info.get("id"):
            continue
        item_cards += 1
        row = parse_item(info, restaurant, category)
        items.setdefault(row["item_id"], row)
    restaurant.setdefault("fssai_license", None)
    restaurant.setdefault("address", None)
    return {"restaurant": restaurant, "items": list(items.values()), "item_cards": item_cards}


def _search_group(data: Dict[str, Any], tab: str) -> List[Dict[str, Any]]:
    for wrapper in _cards(data):
        grouped = (wrapper.get("groupedCard") or {}).get("cardGroupMap") or {}
        if tab in grouped:
            return [_card(c) for c in grouped[tab].get("cards") or []]
    return []


def parse_search_restaurants(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``/dapi/restaurants/search/v3`` with ``selectedPLTab=RESTAURANT`` -> restaurant rows."""
    rows: Dict[str, Dict[str, Any]] = {}
    for card in _search_group(data, "RESTAURANT"):
        if card_type(card) == "Restaurant" and card.get("info"):
            row = parse_restaurant(card["info"])
            rows.setdefault(row["restaurant_id"], row)
    return list(rows.values())


def parse_search_dishes(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``/dapi/restaurants/search/v3`` with ``selectedPLTab=DISH`` -> one row per dish, with its restaurant."""
    rows: List[Dict[str, Any]] = []
    for card in _search_group(data, "DISH"):
        if card_type(card) != "DishGroup":
            continue
        restaurant = parse_restaurant((card.get("restaurant") or {}).get("info") or {})
        for dish in card.get("dishes") or []:
            info = dish.get("info") or {}
            if info.get("id"):
                row = parse_item(info, restaurant)
                row["restaurant_rating"] = restaurant["rating"]
                row["restaurant_promoted"] = restaurant["promoted"]
                row["delivery_time_min"] = restaurant["delivery_time_min"]
                rows.append(row)
    return rows


def parse_listing(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``/dapi/restaurants/list/v5`` (the home page) -> restaurant rows from every restaurant grid."""
    rows: Dict[str, Dict[str, Any]] = {}
    for wrapper in _cards(data):
        card = _card(wrapper)
        grid = ((card.get("gridElements") or {}).get("infoWithStyle") or {}).get("restaurants") or []
        for entry in grid:
            info = entry.get("info") or {}
            if not info.get("id"):
                continue
            link = (entry.get("cta") or {}).get("link")
            row = parse_restaurant(info, url=link if link and link.startswith("http") else None)
            rows.setdefault(row["restaurant_id"], row)
    return list(rows.values())
