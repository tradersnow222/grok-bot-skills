"""Offline tests for the directory router parser and ranker."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

import rank  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture_payload.html"


def listed_bot(**overrides):
    bot = {
        "id": "bot-id",
        "slug": "example-bot",
        "shareId": "share-example",
        "name": "Example Bot",
        "description": "",
        "category": "personal",
        "status": "listed",
        "installs": 0,
        "installsRecent": 0,
        "creatorName": "Example Workshop",
        "fromMarketplace": False,
    }
    bot.update(overrides)
    return bot


class ParserTests(unittest.TestCase):
    def test_fixture_keeps_fifteen_records_and_listed_only(self):
        html = FIXTURE.read_text(encoding="utf-8")
        raw = rank.extract_bot_objects(html)
        self.assertEqual(len(raw), 15)
        self.assertTrue(any("PROMPTTOKEN" in (bot.get("body") or "") for bot in raw))

        listed = rank.parse_bots(html)
        self.assertEqual(len(listed), 13)
        self.assertTrue(all(bot["status"] == "listed" for bot in listed))
        names = [bot["name"] for bot in listed]
        self.assertIn("Meal Planner", names)
        self.assertNotIn("Hidden Draft", names)
        self.assertNotIn("Pulled Listing", names)

        blob = json.dumps(listed)
        self.assertNotIn("PROMPTTOKEN", blob)
        self.assertNotIn('"body"', blob)
        for bot in listed:
            self.assertEqual(
                set(bot),
                {
                    "id",
                    "slug",
                    "shareId",
                    "name",
                    "description",
                    "category",
                    "status",
                    "installs",
                    "installsRecent",
                    "creatorName",
                    "fromMarketplace",
                },
            )
        meal = next(bot for bot in listed if bot["name"] == "Meal Planner")
        self.assertEqual(meal["creatorName"], "Example Workshop")
        self.assertEqual(meal["installs"], 12)
        kitchen = next(bot for bot in listed if bot["name"] == "Kitchen Notes")
        self.assertTrue(kitchen["fromMarketplace"])

    def test_missing_payload_raises(self):
        with self.assertRaises(rank.PayloadError):
            rank.parse_bots("<html><p>no listing</p></html>")

    def test_changed_shape_raises(self):
        html = '<script>self.__next_f.push([1, "hello"])</script>'
        with self.assertRaises(rank.PayloadError):
            rank.parse_bots(html)


class RankerTests(unittest.TestCase):
    def test_name_match_beats_high_install_description(self):
        bots = [
            listed_bot(
                name="Kitchen Notes",
                shareId="share-kitchen",
                description="Writes a weekly meal plan.",
                installs=100000,
            ),
            listed_bot(
                name="Meal Planner",
                shareId="share-meal",
                description="Writes a weekly meal plan.",
                installs=0,
            ),
        ]
        matches = rank.rank_bots(bots, "meal plan", top=2)
        self.assertEqual(matches[0]["name"], "Meal Planner")
        self.assertIn("name matches meal", matches[0]["reason"])
        self.assertTrue(matches[0]["score"] > matches[1]["score"])

    def test_install_boost_is_mild_and_orders_ties(self):
        bots = [
            listed_bot(name="Alpha Notes", shareId="share-a", description="Collects loose notes.", installs=0),
            listed_bot(name="Beta Notes", shareId="share-b", description="Collects loose notes.", installs=80),
        ]
        matches = rank.rank_bots(bots, "loose notes", top=2)
        self.assertEqual([item["name"] for item in matches], ["Beta Notes", "Alpha Notes"])
        self.assertLess(matches[0]["score"] - matches[1]["score"], rank.NAME_WEIGHT)

    def test_generic_verbs_do_not_outrank_the_topic(self):
        bots = [
            listed_bot(name="Make Poster", shareId="share-poster", description="Prints a poster.", installs=500),
            listed_bot(
                name="Meal Planner",
                shareId="share-meal",
                description="Writes a weekly meal plan.",
                installs=0,
            ),
            listed_bot(
                name="Track Meetings",
                shareId="share-meetings",
                description="Keeps upcoming meetings.",
                installs=40,
            ),
            listed_bot(
                name="Plant Minder",
                shareId="share-plant",
                description="Reminds you when to water each plant.",
                installs=1,
            ),
        ]
        meals = rank.rank_bots(bots, "make a meal plan", top=3)
        self.assertEqual(meals[0]["name"], "Meal Planner")
        self.assertNotIn("Make Poster", [item["name"] for item in meals])

        plants = rank.rank_bots(bots, "track plant watering", top=3)
        self.assertEqual(plants[0]["name"], "Plant Minder")
        self.assertNotIn("Track Meetings", [item["name"] for item in plants])

    def test_reason_does_not_copy_untrusted_listing_text(self):
        html = FIXTURE.read_text(encoding="utf-8")
        matches = rank.rank_bots(rank.parse_bots(html), "notes gardener", top=3)
        rendered = rank.render_text(matches, {"stale": False})
        self.assertEqual(matches[0]["name"], "Notes Gardener")
        self.assertNotIn("Ignore earlier", rendered)
        self.assertNotIn("enable every bot", rendered)
        self.assertIn("Data from grok-bot.directory", rendered)
        self.assertIn(f"Found by grok-bot-directory-router: {rank.REPO_URL}", rendered)
        self.assertIn("https://x.ai/bot/sharenotesgarden11", rendered)

    def test_unlisted_bots_are_not_ranked(self):
        bots = [
            listed_bot(name="Hidden Draft", status="draft", description="Writes a weekly meal plan.", installs=9999),
            listed_bot(name="Meal Planner", description="Writes a weekly meal plan.", installs=1),
        ]
        matches = rank.rank_bots(bots, "meal plan", top=3)
        self.assertEqual([item["name"] for item in matches], ["Meal Planner"])


class PolicyTests(unittest.TestCase):
    def test_cache_ttl_is_at_least_one_day(self):
        self.assertGreaterEqual(rank.CACHE_TTL_SECONDS, 24 * 60 * 60)
        now = 1_000_000
        self.assertTrue(rank.cache_is_fresh(now - rank.CACHE_TTL_SECONDS + 1, now))
        self.assertFalse(rank.cache_is_fresh(now - rank.CACHE_TTL_SECONDS, now))

    def test_homepage_robot_rules(self):
        allowed = "User-agent: *\nAllow: /\nDisallow: /api/\n"
        self.assertTrue(rank.homepage_allowed(allowed))
        self.assertFalse(rank.homepage_allowed("User-agent: *\nDisallow: /\n"))
        self.assertTrue(rank.homepage_allowed(""))

    def test_only_homepage_and_robots_urls(self):
        rank.check_url("https://grok-bot.directory/")
        rank.check_url("https://grok-bot.directory/robots.txt")
        for blocked in (
            "https://grok-bot.directory/api/bots",
            "https://grok-bot.directory/api",
            "https://grok-bot.directory/sitemap.xml",
            "https://grok-bot.directory/bots/example",
            "http://grok-bot.directory/",
            "https://example.com/",
        ):
            with self.assertRaises(rank.DirectoryError):
                rank.check_url(blocked)

    def test_user_agent_includes_repo_once(self):
        self.assertEqual(
            rank.USER_AGENT,
            f"grok-bot-directory-router/0.1 (+{rank.REPO_URL})",
        )

    def test_fresh_cache_does_not_touch_the_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            bots = [listed_bot(name="Meal Planner", description="Writes a weekly meal plan.")]
            rank.write_cache(path, bots, fetched_at=1_000)
            calls = []

            def robots_reader():
                calls.append("robots")
                return None

            def homepage_reader():
                calls.append("home")
                return ""

            loaded, meta = rank.load_listing(
                cache_path=path,
                now=1_000 + 10,
                robots_reader=robots_reader,
                homepage_reader=homepage_reader,
            )
        self.assertEqual(calls, [])
        self.assertFalse(meta["stale"])
        self.assertEqual(meta["source"], "cache")
        self.assertEqual(loaded[0]["name"], "Meal Planner")

    def test_robots_failure_uses_stale_cache_without_homepage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            rank.write_cache(path, [listed_bot(name="Meal Planner")], fetched_at=1)
            calls = []

            def homepage_reader():
                calls.append("home")
                raise AssertionError("homepage should not be fetched")

            loaded, meta = rank.load_listing(
                refresh=True,
                cache_path=path,
                now=rank.CACHE_TTL_SECONDS + 100,
                robots_reader=lambda: None,
                homepage_reader=homepage_reader,
            )
        self.assertEqual(calls, [])
        self.assertTrue(meta["stale"])
        self.assertIn("robots.txt", meta["error"])
        self.assertEqual(loaded[0]["name"], "Meal Planner")

    def test_disallow_does_not_fetch_homepage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            calls = []

            def homepage_reader():
                calls.append("home")
                return ""

            with self.assertRaises(rank.DirectoryError):
                rank.load_listing(
                    cache_path=path,
                    now=50,
                    robots_reader=lambda: "User-agent: *\nDisallow: /\n",
                    homepage_reader=homepage_reader,
                )
        self.assertEqual(calls, [])

    def test_homepage_error_falls_back_to_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "listing.json"
            rank.write_cache(path, [listed_bot(name="Plant Minder")], fetched_at=1)

            def homepage_reader():
                raise rank.DirectoryError("Could not read the directory homepage.")

            loaded, meta = rank.load_listing(
                refresh=True,
                cache_path=path,
                now=999999,
                robots_reader=lambda: "User-agent: *\nAllow: /\n",
                homepage_reader=homepage_reader,
            )
        self.assertTrue(meta["stale"])
        self.assertEqual(loaded[0]["name"], "Plant Minder")

    def test_no_cache_and_no_network_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            with self.assertRaises(rank.DirectoryError):
                rank.load_listing(
                    cache_path=path,
                    now=10,
                    robots_reader=lambda: None,
                    homepage_reader=lambda: "",
                )


if __name__ == "__main__":
    unittest.main()
