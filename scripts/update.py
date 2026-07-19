#!/usr/bin/env python3
"""Build the static MIND / MATTER feed from scholarly metadata APIs."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TODAY = dt.date.today()
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "35"))
FROM_DATE = TODAY - dt.timedelta(days=LOOKBACK_DAYS)
OPENALEX_KEY = os.getenv("OPENALEX_API_KEY", "").strip()
USER_AGENT = "mind-matter-research-index/1.0 (static academic discovery site)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

DOMAIN_QUERIES = {
    "consciousness": (
        'consciousness philosophy of mind qualia phenomenology artificial consciousness'
    ),
    "quantum": (
        'quantum foundations measurement problem decoherence entanglement'
    ),
    "neuroscience": (
        'neural correlates consciousness awareness anesthesia'
    ),
}

KEYWORDS = {
    "consciousness": [
        "consciousness", "qualia", "phenomenal", "panpsych", "philosophy of mind",
        "subjective experience", "hard problem", "artificial consciousness", "sentience",
        "higher-order", "illusionism", "mind-body"
    ],
    "quantum": [
        "quantum", "entanglement", "decoherence", "bell inequality", "wave function",
        "measurement problem", "quantum gravity", "quantum information", "superposition"
    ],
    "neuroscience": [
        "neural", "brain", "cortex", "cortical", "neuroscience", "eeg", "fmri", "anesthesia",
        "wakefulness", "awareness", "disorders of consciousness", "thalam", "neuronal"
    ],
}

EVIDENCE_TERMS = {
    "meta-analysis": 12, "systematic review": 10, "randomized": 11, "controlled trial": 10,
    "preregistered": 9, "replication": 9, "longitudinal": 7, "large-scale": 6,
    "causal": 6, "multicenter": 8, "benchmark": 4, "review": 3,
}


def get_json(url: str, params: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    for attempt in range(retries):
        try:
            response = SESSION.get(url, params=params, timeout=45)
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return {}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", value).strip()


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    length = max((max(pos) for pos in index.values() if pos), default=-1) + 1
    words = [""] * length
    for word, positions in index.items():
        for pos in positions:
            if 0 <= pos < length:
                words[pos] = word
    return " ".join(words)


def concise_summary(abstract: str, title: str, max_chars: int = 520) -> str:
    text = clean_text(abstract)
    if not text:
        return f"New work indexed under “{title}.” The source did not provide an abstract; read the original before evaluating its claims."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected = " ".join(sentences[:2])
    if len(selected) < 170 and len(sentences) > 2:
        selected += " " + sentences[2]
    if len(selected) > max_chars:
        selected = selected[:max_chars].rsplit(" ", 1)[0] + "…"
    return selected


def classify_domains(title: str, abstract: str, seed: str | None = None) -> list[str]:
    text = f"{title} {abstract}".lower()
    domains = []
    for domain, words in KEYWORDS.items():
        if domain == seed or any(word in text for word in words):
            domains.append(domain)
    core = [d for d in domains if d != "cross-domain"]
    if len(set(core)) >= 2:
        domains.append("cross-domain")
    return list(dict.fromkeys(domains or ([seed] if seed else [])))


def normalize_type(work_type: str, provider: str, source_type: str = "") -> tuple[str, str]:
    wt = (work_type or "publication").lower()
    if provider == "arXiv" or "preprint" in wt or source_type == "repository":
        return "preprint", "Preprint"
    if "review" in wt:
        return wt, "Review"
    if wt in {"article", "journal-article"}:
        return wt, "Journal article"
    if "book" in wt:
        return wt, "Book / chapter"
    return wt, wt.replace("-", " ").title()


def score_item(item: dict[str, Any]) -> int:
    try:
        age = max(0, (TODAY - dt.date.fromisoformat(item["publication_date"])).days)
    except Exception:
        age = LOOKBACK_DAYS
    freshness = max(0, 36 - age * 1.05)
    citations = min(18, math.log1p(item.get("cited_by_count", 0)) * 5.2)
    evidence = 0
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    for term, weight in EVIDENCE_TERMS.items():
        if term in text:
            evidence = max(evidence, weight)
    peer = 8 if item.get("evidence_label") not in {"Preprint", "Manuscript"} else 2
    access = 3 if item.get("open_access") else 0
    cross = 10 if "cross-domain" in item.get("domains", []) else 0
    abstract_bonus = 4 if item.get("has_abstract") else 0
    return int(max(1, min(100, round(freshness + citations + evidence + peer + access + cross + abstract_bonus))))


def canonical_id(title: str, doi: str = "", external_id: str = "") -> str:
    raw = doi or external_id or re.sub(r"\W+", "", title.lower())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def fetch_openalex() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for domain, query in DOMAIN_QUERIES.items():
        params: dict[str, Any] = {
            "search": query,
            "filter": f"from_publication_date:{FROM_DATE.isoformat()},to_publication_date:{TODAY.isoformat()},is_retracted:false",
            "sort": "publication_date:desc",
            "per_page": 80,
        }
        if OPENALEX_KEY:
            params["api_key"] = OPENALEX_KEY
        try:
            payload = get_json("https://api.openalex.org/works", params)
        except Exception as exc:
            print(f"OpenAlex {domain} failed: {exc}")
            continue
        for work in payload.get("results", []):
            title = clean_text(work.get("display_name"))
            if not title:
                continue
            abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            doi = (work.get("doi") or "").replace("https://doi.org/", "")
            url = work.get("doi") or location.get("landing_page_url") or work.get("id")
            work_type, evidence_label = normalize_type(work.get("type", ""), "OpenAlex", source.get("type", ""))
            authors = [a.get("author", {}).get("display_name") for a in work.get("authorships", [])]
            authors = [a for a in authors if a]
            domains = classify_domains(title, abstract, domain)
            item = {
                "id": canonical_id(title, doi, work.get("id", "")),
                "title": title,
                "authors": authors,
                "summary": concise_summary(abstract, title),
                "publication_date": work.get("publication_date") or TODAY.isoformat(),
                "source": source.get("display_name") or "OpenAlex-indexed source",
                "source_provider": "OpenAlex",
                "url": url,
                "doi": doi,
                "work_type": work_type,
                "evidence_label": evidence_label,
                "open_access": bool((work.get("open_access") or {}).get("is_oa")),
                "cited_by_count": work.get("cited_by_count", 0) or 0,
                "domains": domains,
                "keywords": [k.get("display_name") for k in work.get("keywords", [])[:8] if k.get("display_name")],
                "has_abstract": bool(abstract),
            }
            item["signal_score"] = score_item(item)
            items.append(item)
    return items


def fetch_arxiv() -> list[dict[str, Any]]:
    searches = {
        "quantum": '(all:"quantum foundations" OR all:"measurement problem" OR all:"quantum gravity" OR cat:quant-ph)',
        "neuroscience": '(all:consciousness OR all:"neural correlates" OR all:"disorders of consciousness")',
    }
    items: list[dict[str, Any]] = []
    for domain, search_query in searches.items():
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": 80,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            print(f"arXiv {domain} failed: {exc}")
            continue
        for entry in feed.entries:
            date = (entry.get("published") or "")[:10]
            if not date or date < FROM_DATE.isoformat():
                continue
            title = clean_text(entry.get("title"))
            abstract = clean_text(entry.get("summary"))
            external_id = entry.get("id", "")
            item = {
                "id": canonical_id(title, external_id=external_id),
                "title": title,
                "authors": [a.get("name") for a in entry.get("authors", []) if a.get("name")],
                "summary": concise_summary(abstract, title),
                "publication_date": date,
                "source": "arXiv",
                "source_provider": "arXiv",
                "url": external_id,
                "doi": entry.get("arxiv_doi", ""),
                "work_type": "preprint",
                "evidence_label": "Preprint",
                "open_access": True,
                "cited_by_count": 0,
                "domains": classify_domains(title, abstract, domain),
                "keywords": [tag.get("term") for tag in entry.get("tags", []) if tag.get("term")][:8],
                "has_abstract": bool(abstract),
            }
            item["signal_score"] = score_item(item)
            items.append(item)
    return items


def fetch_europe_pmc() -> list[dict[str, Any]]:
    query = (
        '(TITLE_ABS:"neural correlates of consciousness" OR TITLE_ABS:consciousness OR '
        'TITLE_ABS:"disorders of consciousness" OR TITLE_ABS:awareness OR TITLE_ABS:anesthesia) '
        f'AND FIRST_PDATE:[{FROM_DATE.isoformat()} TO {TODAY.isoformat()}]'
    )
    params = {"query": query, "format": "json", "pageSize": 100, "sort": "FIRST_PDATE_D desc"}
    try:
        payload = get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params)
    except Exception as exc:
        print(f"Europe PMC failed: {exc}")
        return []
    items = []
    for work in (payload.get("resultList") or {}).get("result", []):
        title = clean_text(work.get("title"))
        if not title:
            continue
        abstract = clean_text(work.get("abstractText"))
        doi = work.get("doi", "") or ""
        ext_id = work.get("pmid") or work.get("id") or ""
        url = f"https://europepmc.org/article/{work.get('source','MED')}/{ext_id}" if ext_id else (f"https://doi.org/{doi}" if doi else "https://europepmc.org")
        pub_type = (work.get("pubType") or "article").lower()
        evidence_label = "Review" if "review" in pub_type else ("Preprint" if work.get("source") == "PPR" else "Journal article")
        item = {
            "id": canonical_id(title, doi, ext_id),
            "title": title,
            "authors": [a.strip() for a in (work.get("authorString") or "").split(",") if a.strip()],
            "summary": concise_summary(abstract, title),
            "publication_date": work.get("firstPublicationDate") or work.get("journalInfo", {}).get("printPublicationDate") or TODAY.isoformat(),
            "source": work.get("journalTitle") or "Europe PMC-indexed source",
            "source_provider": "Europe PMC",
            "url": url,
            "doi": doi,
            "work_type": pub_type,
            "evidence_label": evidence_label,
            "open_access": work.get("isOpenAccess") == "Y",
            "cited_by_count": int(work.get("citedByCount") or 0),
            "domains": classify_domains(title, abstract, "neuroscience"),
            "keywords": [],
            "has_abstract": bool(abstract),
        }
        item["signal_score"] = score_item(item)
        items.append(item)
    return items


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        doi = item.get("doi", "").lower().strip()
        title_key = re.sub(r"[^a-z0-9]", "", item.get("title", "").lower())[:180]
        key = f"doi:{doi}" if doi else f"title:{title_key}"
        if key in by_key:
            old = by_key[key]
            old["domains"] = list(dict.fromkeys(old.get("domains", []) + item.get("domains", [])))
            if len(old["domains"]) >= 2 and "cross-domain" not in old["domains"]:
                old["domains"].append("cross-domain")
            old["cited_by_count"] = max(old.get("cited_by_count", 0), item.get("cited_by_count", 0))
            if len(item.get("summary", "")) > len(old.get("summary", "")):
                old["summary"] = item["summary"]
            old["signal_score"] = score_item(old)
        else:
            by_key[key] = item
    return list(by_key.values())


def briefing_for(items: list[dict[str, Any]]) -> dict[str, Any]:
    chosen = []
    used_domains: set[str] = set()
    for item in sorted(items, key=lambda x: (x.get("signal_score", 0), x.get("publication_date", "")), reverse=True):
        primary = next((d for d in item.get("domains", []) if d in {"consciousness", "quantum", "neuroscience"} and d not in used_domains), None)
        if primary:
            chosen.append((primary, item))
            used_domains.add(primary)
        if len(chosen) == 3:
            break
    for item in sorted(items, key=lambda x: x.get("signal_score", 0), reverse=True):
        if len(chosen) >= 3:
            break
        if all(existing[1]["id"] != item["id"] for existing in chosen):
            chosen.append((item.get("domains", ["research"])[0], item))

    domain_names = {"consciousness": "Consciousness / philosophy", "quantum": "Quantum physics", "neuroscience": "Neuroscience"}
    overview = (
        f"Today’s index contains {len(items)} recent records. The strongest signals span "
        + ", ".join(domain_names.get(d, d) for d, _ in chosen)
        + ". Treat the ranking as a reading priority, not a verdict: preprints and ambitious theoretical claims still require independent scrutiny."
    )
    return {
        "date": TODAY.isoformat(),
        "title": "The latest signal",
        "overview": overview,
        "items": [
            {
                "domain": domain,
                "domain_label": domain_names.get(domain, domain.title()),
                "title": item["title"],
                "why_it_matters": item["summary"],
                "url": item["url"],
                "signal_score": item["signal_score"],
                "evidence_label": item["evidence_label"],
            }
            for domain, item in chosen
        ],
    }


def write_rss(briefing: dict[str, Any], items: list[dict[str, Any]]) -> None:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "MIND / MATTER Daily Briefing"
    ET.SubElement(channel, "link").text = os.getenv("SITE_URL", "https://example.github.io/mind-matter/")
    ET.SubElement(channel, "description").text = "New research across consciousness, quantum foundations, and neuroscience."
    ET.SubElement(channel, "lastBuildDate").text = dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    for work in items[:20]:
        node = ET.SubElement(channel, "item")
        ET.SubElement(node, "title").text = work["title"]
        ET.SubElement(node, "link").text = work["url"]
        ET.SubElement(node, "guid").text = work["id"]
        ET.SubElement(node, "description").text = work["summary"]
        try:
            pub = dt.datetime.fromisoformat(work["publication_date"]).replace(tzinfo=dt.timezone.utc)
            ET.SubElement(node, "pubDate").text = pub.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass
    ET.indent(rss)
    ET.ElementTree(rss).write(DATA / "feed.xml", encoding="utf-8", xml_declaration=True)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    collected = fetch_openalex() + fetch_arxiv() + fetch_europe_pmc()
    items = deduplicate(collected)
    items.sort(key=lambda x: (x.get("signal_score", 0), x.get("publication_date", "")), reverse=True)
    items = items[:240]
    feed = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "sources": ["OpenAlex", "arXiv", "Europe PMC"],
        "method_note": "Signal score is a discovery heuristic, not a validity or truth score.",
        "items": items,
    }
    briefing = briefing_for(items)
    (DATA / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "briefing.json").write_text(json.dumps(briefing, ensure_ascii=False, indent=2), encoding="utf-8")
    write_rss(briefing, items)
    print(f"Wrote {len(items)} records to {DATA}")


if __name__ == "__main__":
    main()
