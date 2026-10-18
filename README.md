# Disease-to-Target Protein Discovery Agent

A research-support agent that explores potential disease-to-protein targets from published literature. It uses LangGraph to search PubMed, inspect paper abstracts, identify a small set of literature-supported candidate genes, and verify protein records in UniProtKB.

> **Research use only.** The output is an exploratory hypothesis, not a diagnosis, treatment recommendation, or clinically validated target. Verify every claim against the cited sources and consult domain experts.

## How it works

1. Search PubMed for recent papers related to a disease.
2. Fetch matching abstracts and assess whether they support a disease-to-target relationship.
3. Select up to three candidate gene or protein targets based on the retrieved literature.
4. Query UniProtKB for protein records and summarize the findings with source links.

The agent uses a Groq-hosted Llama model through LangChain and LangGraph. PubMed and UniProtKB are queried through their public APIs.

## Requirements

- Python 3.14 or newer
- A Groq API key
- Internet access

## Setup

1. Create and activate a virtual environment in PowerShell:

   py -3.14 -m venv .venv
   .\.venv\Scripts\Activate.ps1

2. Install dependencies:

   python -m pip install --upgrade pip
   pip install -r requirements.txt

3. Copy the example environment file and add your Groq key:

   Copy-Item .env.example .env

Edit .env and set GROQ_API_KEY. The optional NCBI_EMAIL value can identify requests to NCBI. Keep .env private; it is excluded from Git.

4. Open literature_search_bot.ipynb in PyCharm or Jupyter and run the cells from top to bottom. Enter a disease name when prompted.

## Project files

- literature_search_bot.ipynb — agent implementation and interactive entry point
- requirements.txt — dependencies for a standard pip install
- pyproject.toml and uv.lock — project metadata and locked environment
- .env.example — supported local environment variables, without secrets

## Safety and limitations

- This system is intended for early-stage biomedical research exploration only.
- Model-generated summaries may be incomplete or incorrect. Check linked PubMed records and UniProt entries directly.
- Do not use the output to make patient-care decisions, diagnose disease, or recommend treatment.
- Do not submit identifiable patient information or confidential data.

## Example

At the prompt, enter a disease name such as rheumatoid arthritis. The agent should return a source-backed research hypothesis and supporting literature and protein references. Results depend on available abstracts, API responses, and model behavior.
