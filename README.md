# OCI GenAI Bot with MCP — Invoice Resolution

An agentic system that resolves customer return invoices by finding the original outbound invoice using:

- LangGraph ReAct agent (`main.py`) and MCP tools (`server_invoice_items.py`)
- OCI GenAI (Cohere Command for reasoning; Cohere Embed for embeddings)
- Oracle Autonomous Database (wallet auth) for data and vectors
- Gradio UI (`gradio_app.py`) and Phoenix observability

## Prerequisites

- OCI account with Generative AI service enabled
- Oracle ATP instance + wallet files in `Wallet_ItsmyATPVectorDBs/`
- Python 3.10+ with pip

## Configuration

Configuration is centralized in `config.properties`. `config_loader.py`:

- Reads `config.properties`
- Writes `~/.oci/config` automatically (OCI SDK)
- Sets Oracle DB env vars (e.g., `TNS_ADMIN`)

Example `config.properties`:

```ini
# OCI GenAI
OCI_GENAI_MODEL_ID=cohere.command-plus-latest
OCI_GENAI_EMBEDDING_MODEL_ID=cohere.embed-multilingual-v3.0
OCI_GENAI_ENDPOINT=https://inference.generativeai.us-chicago-1.oci.oraclecloud.com
OCI_COMPARTMENT_OCID=ocid1.tenancy.oc1..xxxx

# OCI API Keys
OCI_USER=ocid1.user.oc1..xxxx
OCI_FINGERPRINT=xx:xx:...
OCI_KEY_FILE=oci_api_key.pem

# Oracle DB
WALLET_PATH=Wallet_ItsmyATPVectorDBs
DB_ALIAS=itsmyatpvectordb_high
USERNAME=ADMIN
PASSWORD=your_password
```

## Quick Start

```powershell
# 1) Install
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) Validate (packages, files, wallet, DB, embeddings)
& .\.venv\Scripts\python.exe .\test_setup.py

# 3) (Optional) Precompute product embeddings
& .\.venv\Scripts\python.exe .\process_vector_products.py

# 4) Run Web UI (recommended)
& .\.venv\Scripts\python.exe .\gradio_app.py
# UI: <http://localhost:7860>  |  Phoenix: <http://localhost:6006>

# Or run CLI
& .\.venv\Scripts\python.exe .\main.py
```

## How It Works

- Flow: vector/fuzzy search product → resolve EAN → search invoices
- MCP tools: `search_vectorized_product`, `resolve_ean`, `search_invoices_by_criteria`
- Phoenix provides traces for prompts, responses, and tool execution

Embeddings note: `process_vector_products.py` uses Sentence-Transformers (384-d) while runtime uses OCI Cohere Embed (1024-d). For best matching, align dimensionality by regenerating DB vectors with OCI or switch runtime embedding to match the offline model. Fuzzy fallback remains available either way.

## Troubleshooting

- Port 7860 busy: stop existing process, then relaunch UI
- Phoenix port 6006 busy: stop the other Phoenix process or disable temporarily
- No semantic results: ensure embeddings table is populated; re-run `process_vector_products.py`
- DB connect issues: verify wallet path (`TNS_ADMIN`), alias in `tnsnames.ora`, and credentials

Logs: tail `app.log`. Phoenix UI: <http://localhost:6006>.

## Structure

```text
OCI_GenAIBot_MCP/
├─ main.py                     # Agent + Phoenix + MCP client (CLI)
├─ gradio_app.py               # Minimal web UI (spawns main.py)
├─ server_invoice_items.py     # MCP server tools
├─ product_search.py           # Vector + fuzzy search
├─ process_vector_products.py  # Precompute and store embeddings
├─ config_loader.py            # Reads config.properties, sets OCI/DB env
├─ test_setup.py               # Environment/DB/embeddings validator
├─ requirements.txt
├─ config.properties
└─ Wallet_ItsmyATPVectorDBs/   # Oracle wallet files
```

## Support

Open Phoenix at <http://localhost:6006> to view traces. For issues, check `app.log` and confirm `test_setup.py` passes.
