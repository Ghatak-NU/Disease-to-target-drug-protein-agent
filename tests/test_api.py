"""API tests. The real agent is swapped for fakes, so these run in milliseconds and cost nothing."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api import app, get_runner  # noqa: E402
from d2t.agent import RESEARCH_LABEL  # noqa: E402


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_runner(fn):
    app.dependency_overrides[get_runner] = lambda: fn


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_page_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Disease-to-Target Agent" in r.text


def test_analyze_happy_path(client):
    seen = []

    def fake(disease):
        seen.append(disease)
        return {"report": f"## LRRK2\n{RESEARCH_LABEL}", "tools_used": ["search_pubmed", "lookup_uniprot"]}

    use_runner(fake)
    r = client.post("/analyze", json={"disease": "  Parkinson's   disease "})
    assert r.status_code == 200
    body = r.json()
    assert seen == ["Parkinson's disease"]  # whitespace normalised before the agent sees it
    assert body["disease"] == "Parkinson's disease"
    assert body["tools_used"] == ["search_pubmed", "lookup_uniprot"]
    assert body["label"] == RESEARCH_LABEL


@pytest.mark.parametrize("payload", [{}, {"disease": ""}, {"disease": " x "}, {"disease": "a" * 101}])
def test_analyze_rejects_bad_input(client, payload):
    use_runner(lambda d: pytest.fail("agent must not run on invalid input"))
    assert client.post("/analyze", json=payload).status_code == 422


def test_missing_api_key_is_503(client):
    def fake(_):
        raise RuntimeError("GROQ_API_KEY is not set")

    use_runner(fake)
    r = client.post("/analyze", json={"disease": "asthma"})
    assert r.status_code == 503
    assert "GROQ" not in r.json()["detail"]  # no config details leaked to callers


def test_upstream_failure_is_502(client):
    def fake(_):
        raise TimeoutError("PubMed timed out")

    use_runner(fake)
    r = client.post("/analyze", json={"disease": "asthma"})
    assert r.status_code == 502
    assert "TimeoutError" in r.json()["detail"]
