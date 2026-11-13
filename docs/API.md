## Run it as a web API

The agent is also packaged as a Python module (`d2t/`) with a FastAPI server, so it can be used
from a browser or any HTTP client rather than only from the notebook.

**Live demo:** <add your Render URL here>

### Run locally
```bash
pip install -r requirements-dev.txt
cp .env.example .env          # add GROQ_API_KEY
uvicorn api:app --reload
```
Open http://127.0.0.1:8000 for the demo page or http://127.0.0.1:8000/docs for interactive docs.

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/analyze` | Run the agent for one disease |

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"disease": "Parkinson'\''s disease"}'
```
Response:
```json
{
  "disease": "Parkinson's disease",
  "report": "## LRRK2 ... Research hypothesis - requires expert validation.",
  "tools_used": ["search_pubmed", "fetch_pubmed_abstracts", "lookup_uniprot"],
  "label": "Research hypothesis - requires expert validation."
}
```
Errors: `422` invalid input (2–100 characters), `503` server missing its API key, `502` the agent
or an upstream API failed.

### Tests
`pytest -q` runs 21 offline tests (parsers, request building, API validation and error
handling). GitHub Actions runs them on every push and pull request.

### Deploy (Render, free tier)
`render.yaml` defines the service. In Render: **New → Blueprint →** this repo, then paste
`GROQ_API_KEY` when asked. The free tier sleeps when idle, so the first request after a pause
takes about a minute.
