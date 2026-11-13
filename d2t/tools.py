"""Plain-Python data tools: PubMed (NCBI E-utilities) and UniProtKB.

These functions hold no LLM code, so they can be unit-tested with a fake
HTTP layer. `agent.py` wraps them as LangChain tools.

Every network call goes through `_get`, which tests replace.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any

import requests

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search"
TIMEOUT_S = 20
MAX_PUBMED_RESULTS = 20
MAX_UNIPROT_RESULTS = 10


def _get(url: str, params: dict[str, Any]) -> requests.Response:
    """Single HTTP entry point (patched in tests)."""
    resp = requests.get(url, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp


def ncbi_params() -> dict[str, str]:
    """Shared E-utilities parameters. NCBI asks callers to identify themselves."""
    params = {"tool": "disease-to-target-agent"}
    email = os.getenv("NCBI_EMAIL")
    if email:
        params["email"] = email
    return params


# ---------------------------------------------------------------- parsers
# Pure functions: response body in, Python data out. Easy to test.


def parse_esearch(payload: dict[str, Any]) -> list[str]:
    return list(payload.get("esearchresult", {}).get("idlist", []))


def parse_esummary(payload: dict[str, Any]) -> list[dict[str, str]]:
    result = payload.get("result", {})
    papers = []
    for pmid in result.get("uids", []):
        doc = result.get(pmid, {})
        papers.append(
            {
                "pmid": pmid,
                "title": doc.get("title", "").strip(),
                "journal": doc.get("fulljournalname") or doc.get("source", ""),
                "pub_date": doc.get("pubdate", ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )
    return papers


def parse_efetch_abstracts(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    records = []
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title_node = article.find(".//ArticleTitle")
        title = "".join(title_node.itertext()) if title_node is not None else ""
        parts = []
        for node in article.iter("AbstractText"):
            text = "".join(node.itertext()).strip()
            label = node.get("Label")
            if text:
                parts.append(f"{label}: {text}" if label else text)
        records.append(
            {
                "pmid": pmid,
                "title": title.strip(),
                "abstract": "\n".join(parts) or "(no abstract available)",
            }
        )
    return records


def parse_uniprot(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for item in payload.get("results", []):
        desc = item.get("proteinDescription", {})
        name = (
            desc.get("recommendedName", {}).get("fullName", {}).get("value")
            or next(
                (s.get("fullName", {}).get("value") for s in desc.get("submissionNames", [])),
                "",
            )
        )
        genes = [g["geneName"]["value"] for g in item.get("genes", []) if "geneName" in g]
        accession = item.get("primaryAccession", "")
        entries.append(
            {
                "accession": accession,
                "entry_name": item.get("uniProtkbId", ""),
                "protein_name": name,
                "genes": genes,
                "organism": item.get("organism", {}).get("scientificName", ""),
                "reviewed": item.get("entryType", "").startswith("UniProtKB reviewed"),
                "url": f"https://www.uniprot.org/uniprotkb/{accession}/entry",
            }
        )
    return entries


def build_uniprot_query(
    gene: str | None = None,
    organism: str | None = "Homo sapiens",
    keyword: str | None = None,
    protein_name: str | None = None,
    reviewed_only: bool = True,
) -> str:
    clauses = []
    if gene:
        clauses.append(f"gene_exact:{gene.strip()}")
    if protein_name:
        clauses.append(f'protein_name:"{protein_name.strip()}"')
    if keyword:
        clauses.append(f'keyword:"{keyword.strip()}"')
    if organism:
        clauses.append(f'organism_name:"{organism.strip()}"')
    if reviewed_only:
        clauses.append("reviewed:true")
    if not (gene or protein_name or keyword):
        raise ValueError("Give at least one of gene, protein_name or keyword.")
    return " AND ".join(clauses)


# ---------------------------------------------------------------- tools


def search_pubmed(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Most recent PubMed papers for a query, with title, journal, date and URL."""
    if not query.strip():
        raise ValueError("query must not be empty")
    max_results = max(1, min(int(max_results), MAX_PUBMED_RESULTS))
    ids = parse_esearch(
        _get(
            f"{EUTILS_BASE}/esearch.fcgi",
            {**ncbi_params(), "db": "pubmed", "term": query, "retmax": max_results,
             "sort": "pub_date", "retmode": "json"},
        ).json()
    )
    if not ids:
        return []
    return parse_esummary(
        _get(
            f"{EUTILS_BASE}/esummary.fcgi",
            {**ncbi_params(), "db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        ).json()
    )


def fetch_pubmed_abstracts(pmids: list[str]) -> list[dict[str, str]]:
    """Titles and abstracts for a list of PMIDs."""
    pmids = [p.strip() for p in pmids if p and p.strip().isdigit()][:MAX_PUBMED_RESULTS]
    if not pmids:
        return []
    xml_text = _get(
        f"{EUTILS_BASE}/efetch.fcgi",
        {**ncbi_params(), "db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
    ).text
    return parse_efetch_abstracts(xml_text)


def lookup_uniprot(
    gene: str | None = None,
    organism: str | None = "Homo sapiens",
    keyword: str | None = None,
    protein_name: str | None = None,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Verify a candidate target in UniProtKB (reviewed entries by default)."""
    query = build_uniprot_query(gene, organism, keyword, protein_name)
    payload = _get(
        UNIPROT_SEARCH,
        {
            "query": query,
            "fields": "accession,id,protein_name,gene_names,organism_name,reviewed",
            "format": "json",
            "size": max(1, min(int(max_results), MAX_UNIPROT_RESULTS)),
        },
    ).json()
    return parse_uniprot(payload)
