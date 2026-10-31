# Rentono AI Service

Smart Property Search Agent using **LangGraph**, **FastMCP**, and **Groq (Llama 3.3)**.

## Architecture

This AI service is completely independent from the Node.js app but shares the same MongoDB database. All AI code lives in the `ai/` folder.

### Folder Structure

```
ai/
├── __init__.py              # Package initialization
├── config.py                # Configuration loading from root .env
├── requirements.txt         # Python dependencies
├── run_agent.py            # CLI entry point for testing the agent
├── main.py                 # FastAPI entry point (Phase 4)
│
├── db/                     # Database layer
│   ├── __init__.py
│   ├── client.py          # (Phase 1) Motor async MongoDB client
│   └── repository.py      # (Phase 1) Raw queries and aggregations
│
├── services/              # Business logic layer (framework-agnostic)
│   ├── __init__.py
│   ├── listing_service.py # (Phase 1) Listing search and filtering
│   └── search_service.py  # (Phase 1) Orchestration helpers
│
├── schemas/               # Pydantic models and DTOs
│   ├── __init__.py
│   ├── intent.py         # (Phase 1) SearchIntent schema
│   └── listing_dto.py    # (Phase 1) RichListing DTO
│
├── mcp_server/           # FastMCP tool server
│   ├── __init__.py
│   ├── server.py        # (Phase 2) MCP server instance
│   └── tools.py         # (Phase 2) Tool implementations
│
└── agent/               # LangGraph workflow
    ├── __init__.py
    ├── state.py        # (Phase 3) Agent state definition
    ├── nodes.py        # (Phase 3) Workflow nodes
    ├── prompts.py      # (Phase 3) Prompt templates
    └── graph.py        # (Phase 3) Graph wiring
```

## Setup

### 1. Install Dependencies

```bash
cd ai
pip install -r requirements.txt
```

### 2. Configure Environment

Add the following to the **root `.env`** file (shared with Node.js app):

```env
# Already exists (shared with Node app)
ATLAS_URL=mongodb+srv://...

# Add this for the AI service
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Verify Configuration

```bash
python -m ai.run_agent
```

Expected output:
```
============================================================
  Rentono AI - Smart Property Search Agent
============================================================

🔧 Verifying configuration...

✓ Configuration loaded successfully!
  • MongoDB: mongodb+srv://...
  • Groq API Key: ******************** (present)
  • AI Service Port: 8000
  • Environment: development

✓ Phase 0 complete: Configuration verified
```

## Development Phases

- **Phase 0**: Scaffolding and configuration ✓
- **Phase 1**: Database layer and services ✓
  - Motor async MongoDB client ✓
  - Listing DTOs and schemas ✓
  - Search and rating services ✓
- **Phase 2**: FastMCP tool server ✓
  - FastMCP 3.4.4 server with @mcp.tool() decorators ✓
  - Tools: list_categories, search_listings, get_listing_by_id ✓
  - FastMCP client for protocol-compliant communication ✓
  - In-memory transport for LangGraph integration ✓
- **Phase 3**: LangGraph agent workflow (intent → retrieve → rank → explain)
- **Phase 4**: FastAPI HTTP endpoint
- **Phase 5**: Node.js integration

## Testing

### Phase 1: Database and Services
```bash
# Verify configuration and test database connection
python -m ai.run_agent
```

### Phase 2: MCP Server and Client
```bash
# Test MCP server tools (direct function calls)
python -m ai.test_mcp

# Test MCP client (full protocol communication)
python -m ai.test_mcp_client
```

### Phase 3: LangGraph Agent (Coming Soon)
```bash
# Test the agent with a natural language query
python -m ai.run_agent "peaceful mountain stay under ₹5000 for a honeymoon"
```

## Design Principles

1. **Shared MongoDB**: Reads from the same database as the Node.js app
2. **Read-only access**: AI service never writes to the database
3. **Services layer**: All business logic lives in `services/` for reuse
4. **Rich DTOs**: Returns complete listing objects, not just IDs
5. **Framework-agnostic core**: Services work with any consumer (MCP, LangGraph, FastAPI)
6. **MCP Protocol**: Tools exposed through FastMCP for LLM agent interaction

## Documentation

- **[SETUP.md](SETUP.md)** - Installation and setup instructions
- **[PHASE1_COMPLETE.md](PHASE1_COMPLETE.md)** - Database and services implementation
- **[PHASE2_COMPLETE.md](PHASE2_COMPLETE.md)** - MCP server and client implementation
- **[MCP_CLIENT_USAGE.md](MCP_CLIENT_USAGE.md)** - FastMCP client usage guide
- **[FASTMCP_MIGRATION.md](FASTMCP_MIGRATION.md)** - FastMCP 3.x migration guide
- **[GROQ_MIGRATION_SUMMARY.md](GROQ_MIGRATION_SUMMARY.md)** - Gemini to Groq migration

## Tech Stack

- **LangGraph**: Agent workflow orchestration
- **Groq (Llama 3.3)**: Ultra-fast LLM for intent parsing, ranking, and explanations
- **FastMCP**: Tool server for the agent
- **Motor**: Async MongoDB driver
- **Pydantic**: Data validation and settings
- **FastAPI**: HTTP API (Phase 4)
