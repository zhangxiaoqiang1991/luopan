import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
spec = importlib.util.spec_from_file_location("sec_fetch", ROOT / "scripts/sec_fetch.py")
sec = importlib.util.module_from_spec(spec); spec.loader.exec_module(sec)


class TestSecFetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tickers = json.loads((FIX / "sec_company_tickers.json").read_text())
        cls.submissions = json.loads((FIX / "sec_submissions.json").read_text())
        cls.facts = json.loads((FIX / "sec_companyfacts.json").read_text())

    def test_resolve_ticker_and_name(self):
        self.assertEqual(sec.resolve_company("aapl", self.tickers)["cik"], "0000320193")
        self.assertEqual(sec.resolve_company("Apple Inc.", self.tickers)["ticker"], "AAPL")

    def test_missing_and_ambiguous_are_not_guessed(self):
        with self.assertRaises(LookupError): sec.resolve_company("missing", self.tickers)
        with self.assertRaises(LookupError): sec.resolve_company("Inc.", self.tickers)

    def test_us_and_foreign_forms_are_located(self):
        self.assertEqual([x["form"] for x in sec.recent_filings(self.submissions)], ["10-Q", "10-Q", "10-K"])
        fpi = json.loads((FIX / "sec_submissions_fpi.json").read_text())
        self.assertEqual([x["form"] for x in sec.recent_filings(fpi)], ["6-K", "20-F"])

    def test_output_has_lineage_and_ignores_custom_tags(self):
        company = sec.resolve_company("AAPL", self.tickers)
        output = sec.build_output(company, self.submissions, self.facts)
        self.assertEqual({x["field"] for x in output["facts"]}, {"revenue", "net_income", "assets"})
        fact = output["facts"][0]
        for key in ("accession", "form", "filed", "period", "unit", "tag", "url", "source_ids"):
            self.assertIn(key, fact)
        self.assertNotIn("MadeUpMetric", json.dumps(output))
        self.assertTrue(all(x["source_ids"][0] in {s["id"] for s in output["sources"]} for x in output["facts"]))

    def test_duplicate_period_facts_do_not_compare_json_objects(self):
        duplicate = json.loads(json.dumps(self.facts))
        observations = duplicate["facts"]["us-gaap"]["Assets"]["units"]["USD"]
        observations.append({**observations[0], "val": 331000000000})
        output = sec.build_output(sec.resolve_company("AAPL", self.tickers), self.submissions, duplicate)
        self.assertIn("assets", {x["field"] for x in output["facts"]})

    def test_user_agent_and_rate_limit_guard(self):
        with self.assertRaises(ValueError): sec.SecClient("anonymous")
        self.assertGreaterEqual(sec.SecClient("luopan test@example.com", min_interval=0).min_interval, .1)


if __name__ == "__main__": unittest.main()
