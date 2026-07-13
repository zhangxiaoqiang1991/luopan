#!/usr/bin/env python3
"""Minimal, auditable SEC EDGAR fetcher for company-research facts."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DATA = "https://data.sec.gov"
BASE_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ALLOWED_FORMS = ("10-K", "10-Q", "20-F", "6-K")

# Standard US-GAAP/IFRS concepts only. Custom issuer tags are intentionally ignored.
CONCEPTS = {
    "revenue": (("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "Revenues"), ("ifrs-full", "Revenue")),
    "net_income": (("us-gaap", "NetIncomeLoss"),
                   ("ifrs-full", "ProfitLoss")),
    "operating_cash_flow": (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
                            ("ifrs-full", "CashFlowsFromUsedInOperatingActivities")),
    "cash": (("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
             ("ifrs-full", "CashAndCashEquivalents")),
    "assets": (("us-gaap", "Assets"), ("ifrs-full", "Assets")),
    "equity": (("us-gaap", "StockholdersEquity"),
               ("ifrs-full", "Equity")),
    "diluted_shares": (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
                       ("ifrs-full", "WeightedAverageNumberOfSharesOutstandingDiluted")),
}


class SecClient:
    def __init__(self, user_agent: str, timeout: float = 20, retries: int = 2,
                 min_interval: float = 0.11):
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC User-Agent must identify the application and include a contact email")
        self.user_agent, self.timeout, self.retries = user_agent, timeout, retries
        self.min_interval, self._last_request = max(min_interval, 0.101), 0.0

    def get_json(self, url: str) -> dict:
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent,
                                                       "Accept": "application/json"})
            try:
                self._last_request = time.monotonic()
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return json.load(response)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                if attempt == self.retries:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError("unreachable")


def resolve_company(query: str, tickers: dict) -> dict:
    q = query.strip().casefold()
    exact_ticker, exact_name, partial = [], [], []
    for item in tickers.values():
        row = {"cik": str(item["cik_str"]).zfill(10), "ticker": item["ticker"],
               "name": item["title"]}
        if item["ticker"].casefold() == q:
            exact_ticker.append(row)
        elif item["title"].casefold() == q:
            exact_name.append(row)
        elif q in item["title"].casefold():
            partial.append(row)
    matches = exact_ticker or exact_name or partial
    if not matches:
        raise LookupError(f"No SEC company matched {query!r}")
    if len(matches) > 1:
        raise LookupError(f"Ambiguous company query {query!r}: " +
                          ", ".join(f"{x['name']} ({x['ticker']})" for x in matches[:8]))
    return matches[0]


def recent_filings(submissions: dict, forms=ALLOWED_FORMS) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    rows = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in forms:
            continue
        accession = recent["accessionNumber"][i]
        primary = recent["primaryDocument"][i]
        cik_plain = str(int(submissions["cik"]))
        url = f"{BASE_ARCHIVES}/{cik_plain}/{accession.replace('-', '')}/{primary}"
        rows.append({"accession": accession, "form": form,
                     "filed": recent["filingDate"][i],
                     "report_date": recent.get("reportDate", [""] * (i + 1))[i],
                     "url": url})
    return rows


def _best_fact(companyfacts: dict, candidates, allowed_accessions: set[str]) -> tuple | None:
    facts = companyfacts.get("facts", {})
    for taxonomy, tag in candidates:
        concept = facts.get(taxonomy, {}).get(tag)
        if not concept:
            continue
        choices = []
        for unit, observations in concept.get("units", {}).items():
            for obs in observations:
                if obs.get("form") not in ALLOWED_FORMS or obs.get("accn") not in allowed_accessions:
                    continue
                choices.append((obs.get("filed", ""), obs.get("end", ""), obs, unit))
        if choices:
            _, _, obs, unit = max(choices, key=lambda item: (item[0], item[1], item[3]))
            return taxonomy, tag, unit, obs
    return None


def build_output(company: dict, submissions: dict, companyfacts: dict) -> dict:
    filings = recent_filings(submissions)
    accession_map = {f["accession"]: f for f in filings}
    facts, sources = [], []
    used = {}
    for field, candidates in CONCEPTS.items():
        found = _best_fact(companyfacts, candidates, set(accession_map))
        if not found:
            continue
        taxonomy, tag, unit, obs = found
        filing = accession_map[obs["accn"]]
        source_id = "src_sec_" + obs["accn"].replace("-", "")
        used[source_id] = {"id": source_id, "title": f"SEC Form {filing['form']} filed {filing['filed']}",
                           "url": filing["url"], "level": "A级", "accession": obs["accn"],
                           "form": filing["form"], "filed": filing["filed"]}
        facts.append({"id": f"fact_{field}_{obs.get('fy') or obs.get('end', 'latest')}",
                      "field": field, "value": obs["val"], "period": obs.get("fp") or obs.get("fy") or obs.get("end"),
                      "period_start": obs.get("start"), "period_end": obs.get("end"),
                      "unit": unit, "taxonomy": taxonomy, "tag": tag,
                      "accession": obs["accn"], "form": obs["form"], "filed": obs["filed"],
                      "url": filing["url"], "source_ids": [source_id], "confidence": "high",
                      "is_calculated": False, "is_inference": False})
    return {"company": {**company, "status": "上市", "market": "SEC"},
            "facts": facts, "sources": list(used.values()), "filings": filings}


def fetch(query: str, client: SecClient) -> dict:
    company = resolve_company(query, client.get_json(TICKERS_URL))
    cik = company["cik"]
    submissions = client.get_json(f"{BASE_DATA}/submissions/CIK{cik}.json")
    companyfacts = client.get_json(f"{BASE_DATA}/api/xbrl/companyfacts/CIK{cik}.json")
    return build_output(company, submissions, companyfacts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("company", help="SEC ticker or exact/unique company name")
    parser.add_argument("--user-agent", required=True, help="App name and contact email")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = fetch(args.company, SecClient(args.user_agent))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
