"""Unit tests for the PubMed/UniProt tools. No network: `_get` is replaced by a fake."""

from __future__ import annotations

import pytest

from d2t import tools

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <ArticleTitle>LRRK2 kinase activity in <i>Parkinson's</i> disease</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">LRRK2 mutations are common.</AbstractText>
          <AbstractText Label="RESULTS">Inhibition reduced toxicity.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>222</PMID>
      <Article><ArticleTitle>No abstract here</ArticleTitle></Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""

UNIPROT_JSON = {
    "results": [
        {
            "primaryAccession": "Q5S007",
            "uniProtkbId": "LRRK2_HUMAN",
            "entryType": "UniProtKB reviewed (Swiss-Prot)",
            "proteinDescription": {
                "recommendedName": {"fullName": {"value": "Leucine-rich repeat serine/threonine-protein kinase 2"}}
            },
            "genes": [{"geneName": {"value": "LRRK2"}}],
            "organism": {"scientificName": "Homo sapiens"},
        },
        {
            "primaryAccession": "A0A000",
            "uniProtkbId": "A0A000_HUMAN",
            "entryType": "UniProtKB unreviewed (TrEMBL)",
            "proteinDescription": {"submissionNames": [{"fullName": {"value": "Uncharacterized protein"}}]},
            "genes": [],
            "organism": {"scientificName": "Homo sapiens"},
        },
    ]
}


class FakeResponse:
    def __init__(self, json_data=None, text=""):
        self._json, self.text = json_data, text

    def json(self):
        return self._json


@pytest.fixture
def calls(monkeypatch):
    """Record every request and answer from a route table keyed on URL suffix."""
    log: list[tuple[str, dict]] = []
    routes: dict[str, FakeResponse] = {}

    def fake_get(url, params):
        log.append((url, params))
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                return resp
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(tools, "_get", fake_get)
    return log, routes


# ---------------------------------------------------------------- parsers

def test_parse_esearch_handles_missing_keys():
    assert tools.parse_esearch({}) == []
    assert tools.parse_esearch({"esearchresult": {"idlist": ["1", "2"]}}) == ["1", "2"]


def test_parse_esummary_builds_links():
    payload = {"result": {"uids": ["111"], "111": {"title": " A title ", "source": "Nat", "pubdate": "2026 Oct"}}}
    [paper] = tools.parse_esummary(payload)
    assert paper == {
        "pmid": "111",
        "title": "A title",
        "journal": "Nat",
        "pub_date": "2026 Oct",
        "url": "https://pubmed.ncbi.nlm.nih.gov/111/",
    }


def test_parse_efetch_keeps_labels_and_inline_markup():
    first, second = tools.parse_efetch_abstracts(EFETCH_XML)
    assert first["pmid"] == "111"
    assert first["title"] == "LRRK2 kinase activity in Parkinson's disease"  # <i> text kept
    assert first["abstract"] == "BACKGROUND: LRRK2 mutations are common.\nRESULTS: Inhibition reduced toxicity."
    assert second["abstract"] == "(no abstract available)"


def test_parse_uniprot_reviewed_and_fallback_name():
    reviewed, unreviewed = tools.parse_uniprot(UNIPROT_JSON)
    assert reviewed["accession"] == "Q5S007"
    assert reviewed["genes"] == ["LRRK2"]
    assert reviewed["reviewed"] is True
    assert reviewed["url"] == "https://www.uniprot.org/uniprotkb/Q5S007/entry"
    assert unreviewed["protein_name"] == "Uncharacterized protein"
    assert unreviewed["reviewed"] is False


def test_build_uniprot_query():
    q = tools.build_uniprot_query(gene="LRRK2")
    assert q == 'gene_exact:LRRK2 AND organism_name:"Homo sapiens" AND reviewed:true'


def test_build_uniprot_query_needs_a_search_term():
    with pytest.raises(ValueError):
        tools.build_uniprot_query(organism="Homo sapiens")


# ---------------------------------------------------------------- tools

def test_search_pubmed_two_step_flow(calls, monkeypatch):
    monkeypatch.setenv("NCBI_EMAIL", "someone@example.org")
    log, routes = calls
    routes["esearch.fcgi"] = FakeResponse({"esearchresult": {"idlist": ["111"]}})
    routes["esummary.fcgi"] = FakeResponse({"result": {"uids": ["111"], "111": {"title": "T"}}})

    papers = tools.search_pubmed("Parkinson disease", max_results=500)

    assert [p["pmid"] for p in papers] == ["111"]
    search_params = log[0][1]
    assert search_params["retmax"] == tools.MAX_PUBMED_RESULTS  # clamped
    assert search_params["sort"] == "pub_date"
    assert search_params["email"] == "someone@example.org"
    assert log[1][1]["id"] == "111"


def test_search_pubmed_no_hits_skips_summary(calls):
    log, routes = calls
    routes["esearch.fcgi"] = FakeResponse({"esearchresult": {"idlist": []}})
    assert tools.search_pubmed("zzzz") == []
    assert len(log) == 1


def test_search_pubmed_rejects_blank_query():
    with pytest.raises(ValueError):
        tools.search_pubmed("   ")


def test_fetch_abstracts_drops_invalid_ids(calls):
    log, routes = calls
    routes["efetch.fcgi"] = FakeResponse(text=EFETCH_XML)
    tools.fetch_pubmed_abstracts(["111", "abc", "", " 222 "])
    assert log[0][1]["id"] == "111,222"


def test_fetch_abstracts_empty_list_makes_no_request(calls):
    log, _ = calls
    assert tools.fetch_pubmed_abstracts(["not-a-pmid"]) == []
    assert log == []


def test_lookup_uniprot(calls):
    log, routes = calls
    routes["uniprotkb/search"] = FakeResponse(UNIPROT_JSON)
    results = tools.lookup_uniprot(gene="LRRK2")
    assert results[0]["accession"] == "Q5S007"
    assert "gene_exact:LRRK2" in log[0][1]["query"]
