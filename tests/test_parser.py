"""Parser tests against fictional API responses in tests/fixtures (same structure as Swiggy's)."""

import json
import os
import unittest

from swiggy_scraper import (
    SwiggyScraper,
    parse_count,
    parse_listing,
    parse_menu,
    parse_search_dishes,
    parse_search_restaurants,
    restaurant_id_from_url,
    rupees,
)

HERE = os.path.dirname(__file__)


def load(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as handle:
        return json.load(handle)["data"]


class HelperTests(unittest.TestCase):
    def test_rupees(self):
        self.assertEqual(rupees(42000), 420)
        self.assertEqual(rupees("12950"), 129.5)
        self.assertIsNone(rupees(None))

    def test_parse_count(self):
        self.assertEqual(parse_count("2.6K+ ratings"), 2600)
        self.assertEqual(parse_count("153 ratings"), 153)
        self.assertEqual(parse_count("1.2L"), 120000)
        self.assertEqual(parse_count("1,372"), 1372)
        self.assertIsNone(parse_count(""))

    def test_restaurant_id_from_url(self):
        self.assertEqual(restaurant_id_from_url("https://www.swiggy.com/city/bangalore/example-house-koramangala-rest5001"), "5001")
        self.assertEqual(restaurant_id_from_url("https://www.swiggy.com/restaurants/example-house-koramangala-bangalore-5001?x=1"), "5001")
        self.assertEqual(restaurant_id_from_url("5001"), "5001")
        self.assertIsNone(restaurant_id_from_url("https://www.swiggy.com/city/bangalore"))


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.menu = parse_menu(load("menu.json"))

    def test_restaurant(self):
        r = self.menu["restaurant"]
        self.assertEqual(r["restaurant_id"], "5001")
        self.assertEqual(r["fssai_license"], "10000000000001")
        self.assertEqual(r["address"], "12 Example Street, Koramangala, Bengaluru 560000")
        self.assertEqual(r["cost_for_two_inr"], 400)
        self.assertEqual(r["rating_count"], 1200)
        self.assertTrue(r["serviceable"])
        self.assertTrue(r["url"].endswith("-rest5001"))

    def test_recommended_duplicates_removed(self):
        self.assertEqual(self.menu["item_cards"], 5)
        self.assertEqual([i["item_id"] for i in self.menu["items"]], ["9001", "9002", "9003"])

    def test_prices_in_rupees(self):
        items = {i["item_id"]: i for i in self.menu["items"]}
        self.assertEqual(items["9001"]["price_inr"], 249)
        self.assertEqual(items["9002"]["price_inr"], 299.5)  # only defaultPrice
        self.assertEqual(items["9001"]["category"], "Biryani")

    def test_variants(self):
        items = {i["item_id"]: i for i in self.menu["items"]}
        self.assertEqual(items["9001"]["variant_prices_inr"], "Half 249; Full 389")
        self.assertEqual(items["9003"]["variant_prices_inr"], "Size: Regular 90; Size: Large 120")

    def test_flags(self):
        items = {i["item_id"]: i for i in self.menu["items"]}
        self.assertTrue(items["9001"]["bestseller"])
        self.assertTrue(items["9001"]["is_veg"])
        self.assertFalse(items["9002"]["is_veg"])
        self.assertFalse(items["9003"]["in_stock"])
        self.assertEqual(items["9002"]["rating_count"], 1500)


class SearchTests(unittest.TestCase):
    def test_restaurants(self):
        rows = parse_search_restaurants(load("search_restaurants.json"))
        self.assertEqual([r["restaurant_id"] for r in rows], ["5001", "5002", "5003"])
        self.assertTrue(rows[0]["promoted"])
        self.assertTrue(rows[2]["veg_only"])
        self.assertEqual(rows[2]["cost_for_two_inr"], 250)
        self.assertEqual(rows[1]["rating_count"], 320)

    def test_dishes(self):
        rows = parse_search_dishes(load("search_dishes.json"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["restaurant_name"], "Example Biryani House")
        self.assertTrue(rows[0]["restaurant_promoted"])
        self.assertEqual(rows[2]["price_inr"], 219)
        self.assertEqual(rows[2]["delivery_time_min"], 35)


class ListingTests(unittest.TestCase):
    def test_listing(self):
        rows = parse_listing(load("listing.json"))
        self.assertEqual([r["restaurant_id"] for r in rows], ["5004", "5003"])
        self.assertEqual(rows[0]["cost_for_two_inr"], 300)
        self.assertEqual(rows[0]["url"], "https://www.swiggy.com/city/bangalore/fictional-cafe-mg-road-rest5004")


class ClientTests(unittest.TestCase):
    def test_token_required(self):
        os.environ.pop("SCRAPEDO_TOKEN", None)
        with self.assertRaises(ValueError):
            SwiggyScraper()

    def test_city(self):
        s = SwiggyScraper(token="x", city="Bangalore")
        self.assertAlmostEqual(s.lat, 12.9715987)
        with self.assertRaises(ValueError):
            SwiggyScraper(token="x", city="atlantis")
        s = SwiggyScraper(token="x", lat=1.5, lng=2.5)
        self.assertEqual((s.lat, s.lng), (1.5, 2.5))


if __name__ == "__main__":
    unittest.main()
