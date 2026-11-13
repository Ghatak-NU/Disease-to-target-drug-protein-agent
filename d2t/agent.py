"""The LangGraph agent: an assistant node that calls tools until it can answer.

Graph:  START -> assistant --(tool calls?)--> tools -> assistant ... -> END
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

from d2t import tools as data

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b"
RESEARCH_LABEL = "Research hypothesis - requires expert validation."
# Hard ceiling on graph steps, so a confused model cannot loop forever (or burn the Groq quota).
RECURSION_LIMIT = 16

SYSTEM_PROMPT = f"""You are a research-support agent that turns a disease name into a short list
of candidate protein targets, grounded in published literature.

Work in three phases:
1. Literature collection - call search_pubmed for recent papers on the disease and its targets.
2. Evidence filtering - call fetch_pubmed_abstracts on the most relevant PMIDs and keep only
   genes/proteins that the abstracts explicitly link to the disease mechanism.
3. Protein verification - for up to three candidates, call lookup_uniprot (gene symbol,
   organism Homo sapiens unless the user says otherwise) and keep only candidates with a record.

Final answer, in Markdown:
- One section per candidate: gene symbol, UniProt accession and link, one-line rationale,
  and the PMIDs (with links) that support it.
- A line stating what evidence was weak or missing.
- End with exactly: "{RESEARCH_LABEL}"

Guardrails:
- Never diagnose, never give treatment or dosing advice.
- Never invent PMIDs, accessions, genes or findings. If the tools return nothing, say so.
- If the input is not a disease or condition, ask for one instead of guessing.
"""


def _as_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _build_tools():
    from langchain_core.tools import tool

    @tool
    def search_pubmed(query: str, max_results: int = 10) -> str:
        """Search PubMed for recent papers. Returns JSON list of {pmid, title, journal, pub_date, url}."""
        return _as_json(data.search_pubmed(query, max_results))

    @tool
    def fetch_pubmed_abstracts(pmids: list[str]) -> str:
        """Fetch titles and abstracts for PubMed IDs. Returns JSON list of {pmid, title, abstract}."""
        return _as_json(data.fetch_pubmed_abstracts(pmids))

    @tool
    def lookup_uniprot(
        gene: str | None = None,
        organism: str | None = "Homo sapiens",
        keyword: str | None = None,
        protein_name: str | None = None,
    ) -> str:
        """Verify a candidate target in UniProtKB (reviewed entries). Returns JSON list of
        {accession, entry_name, protein_name, genes, organism, url}."""
        try:
            return _as_json(data.lookup_uniprot(gene, organism, keyword, protein_name))
        except ValueError as exc:  # let the model correct a bad call instead of crashing the run
            return _as_json({"error": str(exc)})

    return [search_pubmed, fetch_pubmed_abstracts, lookup_uniprot]


@lru_cache(maxsize=1)
def build_graph():
    """Compile the graph once per process (the API reuses it across requests)."""
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")

    from langchain_core.messages import SystemMessage
    from langchain_groq import ChatGroq
    from langgraph.graph import START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode, tools_condition

    agent_tools = _build_tools()
    model = ChatGroq(
        # `or` (not a getenv default) so an empty line in .env still falls back.
        model=os.getenv("GROQ_MODEL") or DEFAULT_MODEL,
        # 0 = repeatable tool calls; the notebook used 1, which is more creative but less reliable.
        temperature=float(os.getenv("GROQ_TEMPERATURE") or 0),
    ).bind_tools(agent_tools)

    def call_model(state: MessagesState):
        return {"messages": [model.invoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])]}

    graph = StateGraph(MessagesState)
    graph.add_node("assistant", call_model)
    graph.add_node("tools", ToolNode(agent_tools))
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", tools_condition)
    graph.add_edge("tools", "assistant")
    return graph.compile()


def run_agent(disease: str) -> dict[str, Any]:
    """Run the agent for one disease. Returns the report and which tools were used, in order."""
    from langchain_core.messages import HumanMessage

    result = build_graph().invoke(
        {"messages": [HumanMessage(f"Disease: {disease}")]},
        config={"recursion_limit": RECURSION_LIMIT},
    )
    messages = result["messages"]
    tools_used = [
        call["name"]
        for msg in messages
        for call in (getattr(msg, "tool_calls", None) or [])
    ]
    report = messages[-1].content if messages else ""
    if RESEARCH_LABEL not in report:
        report = f"{report.rstrip()}\n\n{RESEARCH_LABEL}"
    return {"report": report, "tools_used": tools_used}


if __name__ == "__main__":
    print(run_agent(input("Disease: ").strip())["report"])
