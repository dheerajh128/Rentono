# AI Implementation Status

Last updated: 19 October 2026

This file lists only the Python AI work inside `ai/`. The Node.js app is unchanged. Feature 1 (Smart Property Search Agent) is the only feature in progress. Features 2 and 3 have not been started.

## Progress

| Phase | What it is | Status |
| --- | --- | --- |
| 0 | Folder, config, dependencies | Done |
| 1 | MongoDB access, listing DTOs, search service, Groq LLM wrapper | Done |
| 2 | FastMCP server, three tools, MCP client test | Done |
| 3 | LangGraph workflow: intent, search, rank, explain | Not started |
| 4 | FastAPI HTTP endpoint the Node app can call | Not started |
| 5 | Wire the Node search UI to the Python service | Not started |

Feature 1 is about halfway through the planned build. The data and tool layers work. The agent that understands a sentence, ranks results, and explains them does not exist yet.

Features 2 (travel planning) and 3 (host intelligence) are 0%.

## What exists

```
ai/
├── __init__.py
├── config.py                 # loads root .env (ATLAS_URL, DB_NAME, GROQ_API_KEY)
├── requirements.txt          # LangGraph, LangChain, Groq, FastMCP, Motor, Pydantic
├── run_agent.py              # checks config and prints 3 listings from MongoDB
├── main.py                   # placeholder only (prints that Phase 4 is pending)
├── test_llm.py               # checks Groq via get_llm()
├── test_mcp.py               # calls the three tools directly
├── test_mcp_client.py        # calls the three tools through the MCP client
│
├── db/
│   ├── __init__.py
│   └── client.py             # Motor client, shared Atlas database
│
├── schemas/
│   ├── __init__.py
│   └── listing_dto.py        # ListingDTO, RankedListingDTO, SearchFilters
│
├── services/
│   ├── __init__.py
│   ├── listing_service.py    # search, ratings, get by id, categories
│   └── llm_service.py        # Groq ChatGroq, model openai/gpt-oss-120b
│
├── mcp_server/
│   ├── __init__.py
│   ├── server.py             # FastMCP 3.4.4 server: rentono-listing-server
│   └── tools.py              # list_categories, search_listings, get_listing_by_id
│
└── agent/
    └── __init__.py           # empty package comment only
```

### Working pieces

- Config reads the shared root `.env`. Provider is Groq, not Gemini.
- Database reads are async and read-only. Search, ratings, and lookup live in `listing_service.py`.
- MCP tools are thin wrappers over that service. No search logic is duplicated in the tools.
- The MCP client test uses in-memory transport and the real protocol (`list_tools`, `call_tool`). LangGraph is meant to use this client later instead of importing the tool functions.

### How to check what already works

From the project root:

```bash
python -m ai.run_agent
python -m ai.test_llm
python -m ai.test_mcp
python -m ai.test_mcp_client
```

## Docs in `ai/`

These markdown files are notes from the build. They are not application code.

| File | Contents |
| --- | --- |
| `README.md` | Overview, setup, phase list |
| `PHASE2_COMPLETE.md` | MCP server and client write-up |
| `MCP_CLIENT_USAGE.md` | How to call tools with `fastmcp.Client` |
| `MCP_CLIENT_SUMMARY.md` | Short client recap |
| `IMPLEMENTATION_STATUS.md` | This file |

`README.md` still links to `SETUP.md`, `PHASE1_COMPLETE.md`, `FASTMCP_MIGRATION.md`, and `GROQ_MIGRATION_SUMMARY.md`. Those files are not in the folder.

## What is not built

### Phase 3 — LangGraph (next)

`ai/agent/` has no workflow yet. These files are still missing:

- `agent/state.py` — query, intent, raw results, ranked results, explanation
- `agent/prompts.py` — intent, ranking, and explanation prompts
- `agent/nodes.py` — extract intent, call MCP search, rank with Groq, write the explanation
- `agent/graph.py` — wire the nodes

Also still missing, and needed by that workflow:

- `schemas/intent.py` — structured search intent from a natural-language query

`RankedListingDTO` already exists in `schemas/listing_dto.py`, but nothing fills `score` or `reason` yet.

`run_agent.py` only verifies config and the database. It does not accept a sentence such as “peaceful mountain stay under ₹5000”.

### Phase 4 — HTTP API

`main.py` is a stub. FastAPI and uvicorn are commented out in `requirements.txt`. Planned later:

- `POST /ai/search` — natural-language search
- `GET /health`

### Phase 5 — Node.js

No route, controller, or view calls the Python service. The existing navbar search is still the old title regex search.

### Planned in the README, never added

- `db/repository.py`
- `services/search_service.py`

Search queries live in `listing_service.py` instead. Those two files are not required unless the layer is split later.

## What “done” means for Feature 1

A user types a sentence in the site search. The Node app sends it to Python. LangGraph turns it into filters, searches listings through the MCP client, ranks them with Groq, and returns the listings plus a short reason for each one. If Python is down, the old search still works.

That path is not implemented. Phases 3, 4, and 5 are the remaining work.
