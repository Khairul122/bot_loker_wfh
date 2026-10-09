import tempfile
import unittest
from pathlib import Path

from bot_loker_wfh.github_portfolio import fetch_repos, load_portfolio, relevant_repos, sync_portfolio


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
        portfolio = {"repos": [
            {"name": "JK-WebInventori2-ED", "url": "u1", "language": "PHP", "description": "", "topics": []},
            {"name": "siakad", "url": "u2", "language": "PHP", "description": "", "topics": []},
            {"name": "ecommerce-flutter", "url": "u3", "language": "Dart", "description": "", "topics": []},
        ]}

        stock = relevant_repos(portfolio, "Sistem stok barang gudang untuk UMKM")
        mobile = relevant_repos(portfolio, "Flutter mobile shop app")

        self.assertEqual(stock[0]["name"], "JK-WebInventori2-ED")
        self.assertEqual(mobile[0]["name"], "ecommerce-flutter")
        self.assertEqual(relevant_repos(portfolio, "logo design"), [])  # no fake proof

    def test_sync_saves_and_load_survives_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            self.assertEqual(load_portfolio(path)["repos"], [])
            sync_portfolio("someone", path, get_json=lambda url: [api_repo("a")])
            self.assertEqual(load_portfolio(path)["repos"][0]["name"], "a")


if __name__ == "__main__":
    unittest.main()
