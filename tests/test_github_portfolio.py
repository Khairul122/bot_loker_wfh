import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot_loker_wfh.github_portfolio import fetch_repos, load_portfolio, relevant_repos, sync_portfolio

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def api_repo(name, language="PHP", description="", fork=False):
    return {"name": name, "html_url": f"https://github.com/u/{name}", "language": language,
            "description": description, "topics": [], "fork": fork, "stargazers_count": 0,
            "pushed_at": "2026-10-01T00:00:00Z"}


class GithubPortfolioTest(unittest.TestCase):
    def test_fetch_skips_forks_and_pages_until_short_page(self):
        pages = {1: [api_repo(f"r{i}") for i in range(100)], 2: [api_repo("last"), api_repo("x", fork=True)]}
        calls = []

        def get_json(url):
            calls.append(url)
            return pages[int(url.rsplit("=", 1)[1])]

        repos = fetch_repos("someone", get_json=get_json)

        self.assertEqual(len(repos), 101)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(ValueError):
            fetch_repos("bad/name", get_json=get_json)

    def test_indonesian_project_words_match_repo_names(self):
        fresh = "2026-10-01T00:00:00Z"
        portfolio = {"repos": [
            {"name": "JK-WebInventori2-ED", "url": "u1", "language": "PHP", "description": "stok", "topics": [], "updated_at": fresh},
            {"name": "siakad", "url": "u2", "language": "PHP", "description": "sekolah", "topics": [], "updated_at": fresh},
            {"name": "ecommerce-flutter", "url": "u3", "language": "Dart", "description": "toko", "topics": [], "updated_at": fresh},
        ]}

        stock = relevant_repos(portfolio, "Sistem stok barang gudang untuk UMKM", now=NOW)
        mobile = relevant_repos(portfolio, "Flutter mobile shop app", now=NOW)

        self.assertEqual(stock[0]["name"], "JK-WebInventori2-ED")
        self.assertEqual(mobile[0]["name"], "ecommerce-flutter")
        self.assertEqual(relevant_repos(portfolio, "logo design", now=NOW), [])  # no fake proof

    def test_only_repos_scoring_70_percent_or_more_are_cited(self):
        def repo(name, updated, language="PHP", description="x"):
            return {"name": name, "url": name, "language": language, "description": description, "topics": [], "updated_at": updated}

        portfolio = {"repos": [
            repo("web-inventori-new", "2026-10-01T00:00:00Z"),
            repo("web-inventori-old", "2021-01-01T00:00:00Z", description=""),  # right topic, stale: ranks lower
            repo("JK-WebPendaftaranMagang-ED", "2026-10-01T00:00:00Z"),  # only shares the generic word "web"
            repo("ecommerce-flutter", "2026-10-01T00:00:00Z", language="Dart"),  # other topic entirely
        ]}
        got = relevant_repos(portfolio, "Shopify Website Revamp", now=NOW)
        self.assertEqual(got, [])  # generic words alone never make a match

        got = relevant_repos(portfolio, "Sistem inventori stok gudang", now=NOW)
        self.assertEqual([r["name"] for r in got], ["web-inventori-new", "web-inventori-old"])
        self.assertTrue(got[0]["match"] > got[1]["match"] >= 70)

        # a brief that only shares ONE topic word with a repo is below the bar; the score follows the client's project
        one_word = relevant_repos(portfolio, "Inventori ecommerce toko marketplace", now=NOW, min_match=0)
        self.assertEqual(relevant_repos(portfolio, "Chatbot telegram", now=NOW), [])
        self.assertTrue(all(r["match"] < 100 for r in one_word))

    def test_sync_saves_and_load_survives_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            self.assertEqual(load_portfolio(path)["repos"], [])
            sync_portfolio("someone", path, get_json=lambda url: [api_repo("a")])
            self.assertEqual(load_portfolio(path)["repos"][0]["name"], "a")


if __name__ == "__main__":
    unittest.main()
