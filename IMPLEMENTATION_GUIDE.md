# Implementation Guide - OCI GenAI Bot with MCP

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Oracle Cloud Infrastructure Configuration](#2-oracle-cloud-infrastructure-configuration)
3. [Database Setup](#3-database-setup)
4. [Project Installation](#4-project-installation)
5. [Configuration Details](#5-configuration-details)
6. [Testing and Validation](#6-testing-and-validation)
7. [Gradio Web UI](#7-gradio-web-ui)
8. [Production Deployment](#8-production-deployment)
9. [Advanced Configuration](#9-advanced-configuration)
10. [Troubleshooting Guide](#10-troubleshooting-guide)
11. [Performance Optimization](#11-performance-optimization)

---

## 1. Environment Setup

### 1.1 System Requirements

**Minimum Requirements:**
- **OS**: Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)
- **RAM**: 8GB (16GB recommended)
- **Storage**: 5GB free space
- **Python**: 3.8 or higher
- **Internet**: Stable connection for API calls

### 1.2 Install Python

**Windows:**
```powershell
# Download from python.org or use winget
winget install Python.Python.3.11
```

**macOS:**
```bash
brew install python@3.11
```

**Linux:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### 1.3 Verify Installation

```bash
python --version
pip --version
```

### 1.4 Create Virtual Environment

```bash
# Navigate to project directory
cd c:\Softwares\OCI_GenAIBot_MCP

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Windows CMD:
.\venv\Scripts\activate.bat

# macOS/Linux:
source venv/bin/activate
```

---

## 2. Oracle Cloud Infrastructure Configuration

### 2.1 Create OCI Account

1. Visit [Oracle Cloud](https://www.oracle.com/cloud/free/)
2. Sign up for free tier or use existing account
3. Complete identity verification

### 2.2 Generate API Keys

1. Log into OCI Console
2. Click on **Profile Icon** → **User Settings**
3. Under **Resources**, click **API Keys**
4. Click **Add API Key**
5. Select **Generate API Key Pair**
6. Download private key (`.pem` file)
7. Save the configuration file content

### 2.3 Configure OCI CLI

Create config file at `~/.oci/config` (Windows: `C:\Users\YourName\.oci\config`):

```ini
[DEFAULT]
user=ocid1.user.oc1..aaaaaaaxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
tenancy=ocid1.tenancy.oc1..aaaaaaaxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
region=us-chicago-1
key_file=~/.oci/oci_api_key.pem
```

Place your private key at the `key_file` location.

Note: This application writes `~/.oci/config` automatically from `config.properties` at runtime via `config_loader.py`. Manual CLI setup is optional if you provide the keys in `config.properties`.

### 2.4 Enable Generative AI Service

1. In OCI Console, go to **Analytics & AI** → **Generative AI**
2. Enable the service in your region (e.g., us-chicago-1)
3. Note your **Compartment OCID**

### 2.5 Test OCI Connection

```python
import oci

config = oci.config.from_file("~/.oci/config", "DEFAULT")
identity = oci.identity.IdentityClient(config)
user = identity.get_user(config["user"]).data
print(f"Connected as: {user.name}")
```

---

## 3. Database Setup

### 3.1 Create Oracle Autonomous Database

1. In OCI Console, navigate to **Oracle Database** → **Autonomous Database**
2. Click **Create Autonomous Database**
3. Configure:
   - **Display name**: ItsmyATPVectorDB
   - **Database name**: ATPVECTOR
   - **Workload type**: Transaction Processing
   - **Deployment type**: Shared Infrastructure
   - **Database version**: 19c or higher
   - **OCPU count**: 1 (for testing)
   - **Storage**: 1 TB
   - **Password**: Set secure ADMIN password

4. Click **Create Autonomous Database**
5. Wait for provisioning (5-10 minutes)

### 3.2 Download Database Wallet

1. On the database details page, click **DB Connection**
2. Click **Download Wallet**
3. Set wallet password (same as ADMIN password recommended)
4. Extract wallet files to `Wallet_ItsmyATPVectorDBs/` directory

### 3.3 Create Database Schema

Connect to your database using SQL*Plus, SQL Developer, or execute via Python:

```sql
-- Create products table
CREATE TABLE products (
    id NUMBER PRIMARY KEY,
    code VARCHAR2(100) NOT NULL,
    description VARCHAR2(4000) NOT NULL
);

-- Create embeddings table
CREATE TABLE embeddings_products (
    id NUMBER PRIMARY KEY,
    code VARCHAR2(100),
    description VARCHAR2(4000),
    vector BLOB
);

-- Create invoice table
CREATE TABLE invoice (
    no_invoice VARCHAR2(50) PRIMARY KEY,
    name_customer VARCHAR2(200) NOT NULL,
    state VARCHAR2(2) NOT NULL,
    date_print DATE NOT NULL
);

-- Create invoice items table
CREATE TABLE item_invoice (
    no_invoice VARCHAR2(50) NOT NULL,
    no_item NUMBER NOT NULL,
    code_ean VARCHAR2(50) NOT NULL,
    description_product VARCHAR2(4000),
    value_unitary NUMBER(10,2) NOT NULL,
    PRIMARY KEY (no_invoice, no_item),
    FOREIGN KEY (no_invoice) REFERENCES invoice(no_invoice)
);

-- Create indexes for performance
CREATE INDEX idx_invoice_customer ON invoice(name_customer);
CREATE INDEX idx_invoice_state ON invoice(state);
CREATE INDEX idx_item_ean ON item_invoice(code_ean);
CREATE INDEX idx_item_invoice ON item_invoice(no_invoice);
```

### 3.4 Create Advanced Search Function

```sql
CREATE OR REPLACE FUNCTION fn_advanced_search(p_search_term VARCHAR2)
RETURN SYS_REFCURSOR AS
    v_cursor SYS_REFCURSOR;
BEGIN
    OPEN v_cursor FOR
        SELECT 
            code,
            description,
            UTL_MATCH.JARO_WINKLER_SIMILARITY(UPPER(description), UPPER(p_search_term)) as similarity
        FROM products
        WHERE UTL_MATCH.JARO_WINKLER_SIMILARITY(UPPER(description), UPPER(p_search_term)) > 70
        ORDER BY similarity DESC
        FETCH FIRST 10 ROWS ONLY;
    
    RETURN v_cursor;
END;
/
```

### 3.5 Load Sample Data

```sql
-- Insert sample products
INSERT INTO products (id, code, description) VALUES 
(1, '9788532530787', 'Harry Potter and the Philosopher''s Stone'),
(2, '9780439064873', 'Harry Potter and the Chamber of Secrets'),
(3, '9780439136365', 'Harry Potter and the Prisoner of Azkaban');

-- Insert sample invoices
INSERT INTO invoice (no_invoice, name_customer, state, date_print) VALUES
('INV-001', 'Customer 43', 'RJ', SYSDATE);

-- Insert sample invoice items
INSERT INTO item_invoice (no_invoice, no_item, code_ean, description_product, value_unitary) VALUES
('INV-001', 1, '9788532530787', 'Harry Potter and the Philosopher''s Stone', 139.55);

COMMIT;
```

---

## 4. Project Installation

### 4.1 Clone or Download Project

If you haven't already, obtain the project files and place them in your working directory.

### 4.2 Install Dependencies

```bash
# Make sure virtual environment is activated
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt
```

### 4.3 Verify Installation

```bash
# Check key packages
python -c "import langchain; print('LangChain:', langchain.__version__)"
python -c "import oracledb; print('OracleDB:', oracledb.__version__)"
python -c "import mcp; print('MCP installed successfully')"
```

---

## 5. Configuration Details

This project reads configuration from `config.properties` and writes `~/.oci/config` automatically at runtime. Do not hardcode credentials in source files.

### 5.1 config.properties

Required keys (example values):

```
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

Place the wallet files under `Wallet_ItsmyATPVectorDBs/` in the workspace.

### 5.2 Verify Wallet Alias

Confirm the service alias in `Wallet_ItsmyATPVectorDBs/tnsnames.ora` (e.g., `itsmyatpvectordb_high`) and ensure it matches `DB_ALIAS` in `config.properties`.

### 5.3 Quick Validation

Run the environment validator:

```powershell
python .\test_setup.py
```

It checks packages, wallet files, DB connectivity, and embeddings table presence.

---

## 6. Testing and Validation

### 6.1 Generate Vector Embeddings

This is a crucial step that must be done before running the main application:

```bash
python process_vector_products.py
```

**Expected output:**
```text
📦 Connecting to Oracle Database...
✅ Found 150 products
🧮 Generating embeddings...
💾 Creating embeddings table...
📥 Inserting vectors into database...
✅ All Vectors saved with success in Oracle Database.
```

**Troubleshooting:**
- If table creation fails with "table already exists", that's normal (it's using MERGE)
- Ensure products table has data before running this script
- This process may take a few minutes depending on the number of products

### 6.2 Test MCP Server Standalone

Test the MCP server independently:

```python
# test_mcp_server.py
import asyncio
from server_invoice_items import search_vectorized_product, resolve_ean

async def test_mcp():
    # Test vector search
    result = search_vectorized_product("Harry Potter")
    print("Vector Search Result:", result)
    
    # Test EAN resolution
    ean_result = resolve_ean("Harry Potter")
    print("EAN Result:", ean_result)

asyncio.run(test_mcp())
```

### 6.3 Test Complete System

#### Option A: Gradio Web UI (Recommended)

Start the Gradio application:

```powershell
python .\gradio_app.py
```

Expected:

```text
🌅 Phoenix running on http://localhost:6006
🛠️ Loaded tools: ['search_vectorized_product', 'resolve_ean', 'search_invoices_by_criteria']
🤖 Agent ready to process queries
Gradio app running on http://localhost:7860
```

Access:

- UI: <http://localhost:7860>
- Phoenix: <http://localhost:6006>

#### Option B: Command-Line Interface

Start the CLI application:

```bash
python main.py
```

**Expected startup sequence:**
```text
🌅 Phoenix running on http://localhost:6006
📦 Loading Oracle Vectors...
🛠️ Loaded tools: ['search_vectorized_product', 'resolve_ean', 'search_invoices_by_criteria']
🤖 READY
You: 
```

### 6.4 Test Queries

**Test Query 1: Simple Product Search**
```text
Search for products similar to "Harry Potter"
```

**Test Query 2: Complete Invoice Resolution**
```text
Find invoice for Customer 43, product description "Harry Potter", price 139.55, location RJ
```

**Test Query 3: Partial Information**
```text
Find invoices for Customer 43 in RJ
```

### 6.5 Test Web Interface Features

Using the Gradio web interface:

1. Status pill transitions: Initializing → Active → Inactive
2. Chat input: Enter to submit; Shift+Enter for newline
3. Restart Agent: Click the button to restart `main.py`
4. Full responses: Verify multi-line responses render correctly
5. Logs: Tail `app.log` for interactions and errors

### 6.6 Verify Observability

1. Open browser to <http://localhost:6006>
2. Navigate to **Traces** tab
3. Verify traces are being captured
4. Check trace details for tool calls and responses

### 6.7 Test Configuration Script

Run the automated test script:

```bash
python test_setup.py
```

This will verify:
- All packages are installed
- Files are in place
- Database connection works
- Embeddings are loaded

---

## 7. Gradio Web UI

The web interface is implemented with Gradio and starts the agent (`main.py`) as a subprocess, showing a status pill and a chat.

### 7.1 Run the UI

```powershell
python .\gradio_app.py
```

- UI: <http://localhost:7860>
- Phoenix: <http://localhost:6006>

### 7.2 Features

- Status: Initializing → Active → Inactive (with spinner)
- Enter to submit; Shift+Enter for newline
- “Restart Agent” button to gracefully restart `main.py`
- Full multi-line assistant messages (uses ASSIST_BEGIN/ASSIST_END markers)

### 7.3 Logs and Monitoring

- Application log: `app.log`
- Phoenix traces: <http://localhost:6006> (LLM prompt/response and tool spans)

---

## 8. Production Deployment

### 8.1 Production Considerations

**Security:**

- Never commit credentials to version control
- Use environment variables for sensitive data
- Rotate API keys regularly
- Use read-only database users when possible

**Create `.env` file:**
```env
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxxx
DB_PASSWORD=your_secure_password
DB_USERNAME=ADMIN
DB_WALLET_PASSWORD=your_wallet_password
```

**Update code to use environment variables:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

PASSWORD = os.getenv("DB_PASSWORD")
COMPARTMENT_ID = os.getenv("OCI_COMPARTMENT_ID")
```

### 8.2 Create `.gitignore`

```gitignore
# Virtual Environment
venv/
env/
.venv/

# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd

# Environment variables
.env
.env.local

# Oracle Wallet - CRITICAL: Never commit wallet files!
Wallet_*/
*.sso
*.p12
*.pem
*.jks

# OCI config
.oci/

# Logs
*.log
logs/

# Phoenix data
.phoenix/

# IDE
.vscode/
.idea/
*.swp
*.swo
```

### 8.3 Dockerization (Optional)

**Create `Dockerfile`:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY *.py .
COPY Wallet_ItsmyATPVectorDBs/ ./Wallet_ItsmyATPVectorDBs/

# Set environment
ENV TNS_ADMIN=/app/Wallet_ItsmyATPVectorDBs

# Run application
CMD ["python", "main.py"]
```

**Build and run:**
```bash
docker build -t oci-genai-bot .
docker run -it --rm oci-genai-bot
```

### 8.4 Deployment to OCI Compute

1. Create OCI Compute instance
2. Install Python and dependencies
3. Copy project files (excluding wallet initially)
4. Download wallet directly on instance
5. Configure OCI credentials using instance principal
6. Run as systemd service

**Create systemd service:**
```ini
[Unit]
Description=OCI GenAI Bot
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/OCI_GenAIBot_MCP
Environment="PATH=/home/opc/OCI_GenAIBot_MCP/venv/bin"
ExecStart=/home/opc/OCI_GenAIBot_MCP/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 9. Advanced Configuration

### 9.1 Tuning Search Parameters

**In `product_search.py`:**

```python
searcher = SearchSimilarProduct(
    top_k=5,              # Number of results to return
    minimal_distance=1.0  # Maximum distance threshold
)
```

**Adjust for your use case:**

- **Stricter matching**: Lower `minimal_distance` (e.g., 0.5)
- **More lenient**: Higher `minimal_distance` (e.g., 1.5)
- **More results**: Increase `top_k` (e.g., 10)

### 9.2 Model Configuration

**Temperature:** Controls randomness (0.0 = deterministic, 1.0 = creative)
```python
model_kwargs={"temperature": 0.1, "top_p": 0.75, "max_tokens": 2000}
```

**For invoice resolution:**

- Use low temperature (0.0-0.2) for consistent results
- Increase max_tokens if responses are truncated

### 9.3 Embeddings Alignment

The runtime agent embeds queries with OCI GenAI Cohere (e.g., `cohere.embed-multilingual-v3.0`, 1024-d). The offline product embeddings script (`process_vector_products.py`) uses Sentence-Transformers (default 384-d). For best matching:

- Option A: Regenerate product embeddings with OCI Cohere Embed to match runtime dimensionality.
- Option B: Switch runtime query embedding in `product_search.py` to the same Sentence-Transformers model used offline.

Fuzzy matching remains as a fallback regardless of dimensionality.

### 9.4 Database Connection Pooling

For production, implement connection pooling:

```python
import oracledb

# Create connection pool
pool = oracledb.create_pool(
    user=USERNAME,
    password=PASSWORD,
    dsn=DB_ALIAS,
    config_dir=WALLET_PATH,
    wallet_location=WALLET_PATH,
    wallet_password=PASSWORD,
    min=2,
    max=10,
    increment=1
)

# Use pool
connection = pool.acquire()
# ... do work ...
connection.close()
```

### 9.5 Custom System Prompts

Modify the agent's behavior by editing the system prompt in `main.py`:

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", """
        Custom instructions here...
        - Add domain-specific knowledge
        - Modify search strategy
        - Change response format
    """),
    ("placeholder", "{messages}")
])
```

---

## 10. Troubleshooting Guide

### 10.1 Common Issues

**Issue: "No MCP tools were loaded"**

**Cause:** MCP server not starting properly

**Solution:**
```bash
# Test server directly
python server_invoice_items.py

# Check Python path
which python  # macOS/Linux
where python  # Windows

# Verify in main.py
"command": "python",  # Change to full path if needed
"args": ["server_invoice_items.py"],
```

**Issue: "DPI-1047: Cannot locate a 64-bit Oracle Client library"**

**Cause:** Oracle Instant Client not found

**Solution (Windows):**

1. Download Oracle Instant Client
2. Extract to `C:\oracle\instantclient_19_x`
3. Add to PATH environment variable

**Solution (Linux):**
```bash
sudo apt-get install libaio1
```

**Issue: "ORA-12154: TNS:could not resolve the connect identifier"**

**Cause:** Wallet configuration issue

**Solution:**

- Verify `TNS_ADMIN` environment variable
- Check wallet files are present
- Confirm alias name in `tnsnames.ora`
- Ensure wallet password is correct

**Issue: Vector search returns no results**

**Cause:** Embeddings not generated

**Solution:**
```bash
# Regenerate embeddings
python process_vector_products.py

# Verify embeddings table
# Run SQL: SELECT COUNT(*) FROM embeddings_products;
```

**Issue: "Connection refused" to Phoenix**

**Cause:** Phoenix not starting

**Solution:**
```python
# Comment out Phoenix in main.py for testing
# px.launch_app()
```

### 10.2 Debug Mode

Enable detailed logging:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add to main.py
logger = logging.getLogger(__name__)
logger.debug("Debug information here")
```

### 10.3 Performance Issues

**Slow embedding generation:**

- Use GPU-accelerated Sentence Transformers
- Batch process products
- Cache embeddings

**Slow database queries:**

- Add appropriate indexes
- Use EXPLAIN PLAN to analyze queries
- Consider partitioning large tables

---

## 11. Performance Optimization

### 11.1 Database Optimization

**Add vector index (Oracle 23c+):**
```sql
CREATE VECTOR INDEX idx_embeddings_vector 
ON embeddings_products(vector)
PARAMETERS('DISTANCE=EUCLIDEAN');
```

**Optimize invoice search:**
```sql
CREATE INDEX idx_item_composite 
ON item_invoice(code_ean, value_unitary, no_invoice);
```

### 11.2 Caching Strategy

Implement Redis caching for frequent queries:

```python
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def cached_search(query):
    # Check cache
    cached = redis_client.get(f"search:{query}")
    if cached:
        return json.loads(cached)
    
    # Perform search
    result = search_vectorized_product(query)
    
    # Cache result (TTL: 1 hour)
    redis_client.setex(
        f"search:{query}",
        3600,
        json.dumps(result)
    )
    
    return result
```

### 11.3 Batch Processing

Process multiple queries in parallel:

```python
import asyncio

async def batch_search(queries):
    tasks = [search_vectorized_product(q) for q in queries]
    return await asyncio.gather(*tasks)
```

### 11.4 Model Optimization

**Use smaller, faster models for simple queries:**
```python
# For simple lookups
model_kwargs={"temperature": 0.0, "max_tokens": 500}

# For complex reasoning
model_kwargs={"temperature": 0.2, "max_tokens": 2000}
```

### 11.5 Monitoring Metrics

Track key metrics:

- Query response time
- Database connection pool stats
- Cache hit rate
- Token usage (for cost optimization)
- Error rates

```python
import time

def monitor_query(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        print(f"Query took {duration:.2f}s")
        return result
    return wrapper
```

---

## Appendix A: Database Schema Reference

Complete schema with all constraints:

```sql
-- Full schema creation script
CREATE TABLE products (
    id NUMBER PRIMARY KEY,
    code VARCHAR2(100) NOT NULL UNIQUE,
    description VARCHAR2(4000) NOT NULL,
    category VARCHAR2(100),
    created_date DATE DEFAULT SYSDATE
);

CREATE TABLE embeddings_products (
    id NUMBER PRIMARY KEY,
    code VARCHAR2(100),
    description VARCHAR2(4000),
    vector BLOB,
    model_version VARCHAR2(50),
    created_date DATE DEFAULT SYSDATE,
    CONSTRAINT fk_embedding_product FOREIGN KEY (id) REFERENCES products(id)
);

CREATE TABLE invoice (
    no_invoice VARCHAR2(50) PRIMARY KEY,
    name_customer VARCHAR2(200) NOT NULL,
    state VARCHAR2(2) NOT NULL,
    date_print DATE NOT NULL,
    total_amount NUMBER(12,2),
    created_date DATE DEFAULT SYSDATE
);

CREATE TABLE item_invoice (
    no_invoice VARCHAR2(50) NOT NULL,
    no_item NUMBER NOT NULL,
    code_ean VARCHAR2(50) NOT NULL,
    description_product VARCHAR2(4000),
    quantity NUMBER(10,2) NOT NULL,
    value_unitary NUMBER(10,2) NOT NULL,
    total_value NUMBER(12,2),
    PRIMARY KEY (no_invoice, no_item),
    CONSTRAINT fk_item_invoice FOREIGN KEY (no_invoice) REFERENCES invoice(no_invoice) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_invoice_customer ON invoice(UPPER(name_customer));
CREATE INDEX idx_invoice_state ON invoice(state);
CREATE INDEX idx_invoice_date ON invoice(date_print);
CREATE INDEX idx_item_ean ON item_invoice(code_ean);
CREATE INDEX idx_item_price ON item_invoice(value_unitary);
```

---

## Appendix B: API Reference

### MCP Server Tools

**search_vectorized_product**

- **Input**: `description: str`
- **Output**: `dict` with semantic and fuzzy results
- **Use case**: Initial product lookup

**resolve_ean**

- **Input**: `description: str`
- **Output**: `dict` with code, description, similarity
- **Use case**: Get definitive EAN code

**search_invoices_by_criteria**
- **Input**: `customer, state, price, ean, margin`
- **Output**: `list` of matching invoices
- **Use case**: Find original invoice

---

## Appendix C: Example Scenarios

### Scenario 1: Exact Match
```text
Input: "Harry Potter and the Philosopher's Stone"
Expected: Direct EAN match, invoice found
```

### Scenario 2: Fuzzy Match
```text
Input: "Harry Poter" (typo)
Expected: Fuzzy matching corrects to "Harry Potter", invoice found
```

### Scenario 3: Partial Information
```text
Input: Only customer and state
Expected: Multiple results returned
```

### Scenario 4: No Match
```text
Input: Completely unknown product
Expected: "EAN not found with the provided criteria."
```

---

## Support and Resources

- **OCI Documentation**: <https://docs.oracle.com/en-us/iaas/Content/home.htm>
- **LangChain Docs**: <https://python.langchain.com/>
- **MCP Protocol**: <https://modelcontextprotocol.io/>
- **Oracle Database**: <https://docs.oracle.com/en/database/>

---

**Document Version**: 1.0  
**Last Updated**: November 2025  
**Maintained By**: [Your Team Name]
