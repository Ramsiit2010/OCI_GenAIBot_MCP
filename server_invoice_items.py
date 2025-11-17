# -*- coding: utf-8 -*-
import os
import logging
from pathlib import Path
from datetime import datetime
import oracledb
import zipfile
from mcp.server.fastmcp import FastMCP
from product_search import SearchSimilarProduct

# Configure logging (UTF-8 file, PID in format)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from config_loader import load_properties, apply_db_env

logger.info("Initializing Invoice Items MCP Server...")

# Load DB env from config
PROPS = load_properties(str(Path(os.getcwd())/ 'config.properties'))
apply_db_env(PROPS)

sercher = SearchSimilarProduct()
logger.info("✅ SearchSimilarProduct initialized")

mcp = FastMCP("InvoiceItemResolver")
# Oracle Wallet Configuration from env/config
WALLET_PATH = os.environ.get("TNS_ADMIN") or PROPS.get("WALLET_PATH", "Wallet_ItsmyATPVectorDBs")
DB_ALIAS = os.environ.get("DB_ALIAS") or PROPS.get("DB_ALIAS", "itsmyatpvectordb_high")
USERNAME = os.environ.get("DB_USERNAME") or PROPS.get("USERNAME", "ADMIN")
PASSWORD = os.environ.get("DB_PASSWORD") or PROPS.get("PASSWORD", "")
if WALLET_PATH:
    os.environ["TNS_ADMIN"] = WALLET_PATH


def execute_query(query: str, params: dict = {}):
    try:
        logger.debug(f"Executing query with params: {params}")
        connection = oracledb.connect(
            user=USERNAME,
            password=PASSWORD,
            dsn=DB_ALIAS,
            config_dir=WALLET_PATH,
            wallet_location=WALLET_PATH,
            wallet_password=PASSWORD
        )
        cursor = connection.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        connection.close()
        logger.debug(f"Query returned {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"Database query error: {e}", exc_info=True)
        print(f"[ERROR]: {e}")
        return []

def execute_ean_search(search_terms):
    results = []

    try:
        logger.debug(f"Executing EAN search for: {search_terms}")
        connection = oracledb.connect(
            user=USERNAME,
            password=PASSWORD,
            dsn=DB_ALIAS,
            config_dir=WALLET_PATH,
            wallet_location=WALLET_PATH,
            wallet_password=PASSWORD
        )
        cursor = connection.cursor()

        query = """
                SELECT * FROM TABLE(fn_advanced_search(:1))
                ORDER BY similarity DESC \
                """
        cursor.execute(query, [search_terms])

        for row in cursor:
            results.append({
                "code": row[0],
                "description": row[1],
                "similarity": row[2]
            })

        cursor.close()
        connection.close()
        logger.debug(f"EAN search returned {len(results)} results")
    except Exception as e:
        logger.error(f"EAN search error: {e}", exc_info=True)
        return {"error": str(e)}, 500

    return results
# --------------------- MCP TOOLS ---------------------
@mcp.tool()
def search_vectorized_product(description: str) -> dict:
    """
        Searches for a product by description using embeddings.
    """
    logger.info(f"MCP Tool: search_vectorized_product called with: {description[:50]}...")
    result = sercher.search_similar_products(description)
    logger.info(f"search_vectorized_product returned {len(result.get('semantics', []))} semantic results")
    return result

@mcp.tool()
def resolve_ean(description: str) -> dict:
    """
        Resolves the product's EAN code based on its description.
    """
    logger.info(f"MCP Tool: resolve_ean called with: {description[:50]}...")
    result = execute_ean_search(description)

    if isinstance(result, list) and result:
        logger.info(f"resolve_ean found EAN: {result[0]['code']}")
        return {
            "code": result[0]["code"],
            "description": result[0]["description"],
            "similarity": result[0]["similarity"]
        }
    else:
        logger.warning("resolve_ean: No EAN found")
        return {"error": "Search not found by EAN."}

@mcp.tool()
def search_invoices_by_criteria(customer: str = None, state: str = None, price: float = None, ean: str = None, margin: float = 0.05) -> list:
    """
        Searches for outbound invoices based on customer, state, EAN, and approximate price.
        Allows one or more fields to be omitted.
        As long as an EAN has not been established, it is not useful to use this service.
    """
    logger.info(f"MCP Tool: search_invoices_by_criteria called - customer={customer}, state={state}, ean={ean}, price={price}")

    query = """
            SELECT nf.no_invoice, nf.name_customer, nf.state, nf.date_print,
                   inf.no_item, inf.code_ean, inf.description_product, inf.value_unitary
            FROM invoice nf
                     JOIN item_invoice inf ON nf.no_invoice = inf.no_invoice
            WHERE 1=1 
            """

    params = {}

    #if customer:
    query += " AND LOWER(nf.name_customer) LIKE LOWER(:customer)"
    params["customer"] = f"%{customer}%"
    #if state:
    query += " AND LOWER(nf.state) = LOWER(:state)"
    params["state"] = state
    #if ean:
    query += " AND inf.code_ean = :ean"
    params["ean"] = ean
    if price is not None:
        query += " AND inf.value_unitary BETWEEN :price_min AND :price_max"
        params["price_min"] = price * (1 - margin)
        params["price_max"] = price * (1 + margin)

    result = execute_query(query, params)
    logger.info(f"search_invoices_by_criteria found {len(result)} invoices")

    return [
        dict(zip(
            ["no_invoice", "name_customer", "state", "date_print", "no_item", "code_ean", "description_product", "value_unitary"],
            row
        ))
        for row in result
    ]


# --------------------- EXECUÇÃO MCP ---------------------

if __name__ == "__main__":
    # Start the MCP server
    logger.info("="*60)
    logger.info("Starting MCP Server - InvoiceItemResolver")
    logger.info("="*60)
    mcp.run(transport="stdio")