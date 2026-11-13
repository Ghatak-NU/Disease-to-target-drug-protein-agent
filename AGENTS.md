# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot) working in this repo.

## What this is
An LLM agent that goes from a disease name to up to three candidate protein targets.
It searches PubMed, reads abstracts and verifies each candidate in UniProtKB.
It is research support only: the output is a hypothesis, never medical advice.

## Layout
| Path | Role |
|---|---|
| `d2t/tools.py` | PubMed + UniProt HTTP calls and **pure parsers**. No LLM code. Every request goes through `_get`. |
| `d2t/agent.py` | LangGraph graph (assistant ⇄ tools), system prompt, `run_agent()`. |
| `api.py` | FastAPI app: `GET /health`, `POST /analyze`, demo page at `/`. |
| `static/index.html` | Single-file demo UI (no build step). |
| `tests/` | pytest. `test_tools.py` fakes `_get`; `test_api.py` overrides `get_runner`. |
| `literature_search_bot.ipynb` | Original prototype notebook (kept for history). |
| `render.yaml` | Render deployment blueprint. |

## Commands
```bash
pip install -r requirements-dev.txt
pytest -q                      # must pass before any PR; needs no API key or network
uvicorn api:app --reload       # local server at http://127.0.0.1:8000
python -m d2t.agent            # one run from the terminal (needs GROQ_API_KEY)
```

## Rules
- Tests never touch the network or the LLM. New HTTP calls go through `tools._get`; new agent
  behaviour is tested through the `get_runner` dependency override.
- Keep `tools.py` free of LangChain imports so the parsers stay fast to test.
- Do not weaken the guardrails in `SYSTEM_PROMPT` (no diagnosis, no treatment advice, no
  invented PMIDs/accessions) or remove the `RESEARCH_LABEL` line from reports.
- Secrets live in `.env` (local) or Render environment variables. Never commit `.env`.
- The API must not leak internals: error responses give the exception type, not the message.
- Small PRs, one concern each, with a description of what changed and why.

## Pitfalls (add each real agent mistake here when you catch it in review)
- Adding `async def` to `/analyze` while calling the blocking agent inside it. That blocks the
  event loop; keep it a plain `def`.
- Guessing UniProt query field names. Check them against the UniProt REST docs before changing
  `build_uniprot_query`.
- Writing tests that only assert the fake's return value. A test must fail if the code under
  test breaks (check request params, error paths, validation).
