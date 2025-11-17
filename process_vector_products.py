import oracledb
import zipfile
import os
from pathlib import Path
import logging
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info("="*60)
logger.info(f"Starting Vector Processing - {datetime.now()}")
logger.info("="*60)

from config_loader import load_properties, apply_db_env

# === ORACLE CONFIGURATION WITH WALLET ===
PROPS = load_properties(str(Path(os.getcwd())/ 'config.properties'))
apply_db_env(PROPS)
WALLET_PATH = os.environ.get("TNS_ADMIN") or PROPS.get("WALLET_PATH", "Wallet_ItsmyATPVectorDBs")
DB_ALIAS = os.environ.get("DB_ALIAS") or PROPS.get("DB_ALIAS", "itsmyatpvectordb_high")
USERNAME = os.environ.get("DB_USERNAME") or PROPS.get("USERNAME", "ADMIN")
PASSWORD = os.environ.get("DB_PASSWORD") or PROPS.get("PASSWORD", "")
if WALLET_PATH:
    os.environ["TNS_ADMIN"] = WALLET_PATH

# === CONNECTING USING oracledb (thin mode) ===
logger.info("Connecting to Oracle Database...")
try:
    connection = oracledb.connect(
        user=USERNAME,
        password=PASSWORD,
        dsn=DB_ALIAS,
        config_dir=WALLET_PATH,
        wallet_location=WALLET_PATH,
        wallet_password=PASSWORD
    )
    logger.info("✅ Database connection established")
except Exception as e:
    logger.error(f"❌ Failed to connect to database: {e}", exc_info=True)
    raise

cursor = connection.cursor()

# === CONSULT THE PRODUCT TABLE ===
logger.info("Querying products table...")
cursor.execute("SELECT id, code, description FROM products")
rows = cursor.fetchall()
logger.info(f"✅ Retrieved {len(rows)} products from database")

ids = []
descriptions = []

for row in rows:
    ids.append((row[0], row[1], row[2]))
    descriptions.append(row[2])

# === EMBEDDING GENERATION ===
logger.info("Loading Sentence Transformer model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
logger.info("✅ Model loaded successfully")

logger.info("Generating embeddings for all products...")
embeddings = model.encode(descriptions, convert_to_numpy=True)
logger.info(f"✅ Generated {len(embeddings)} embeddings")

# === CREATION OF EMBEDDINGS TABLE (if it does not exist) ===
logger.info("Creating/verifying embeddings_products table...")
cursor.execute("""
               BEGIN
                   EXECUTE IMMEDIATE '
            CREATE TABLE embeddings_products (
                id NUMBER PRIMARY KEY,
                code VARCHAR2(100),
                description VARCHAR2(4000),
                vector BLOB
            )';
               EXCEPTION
                   WHEN OTHERS THEN
                       IF SQLCODE != -955 THEN
                           RAISE;
                       END IF;
               END;
               """)
logger.info("✅ Table verified/created")

# === INSERTING OR UPDATING DATA ===
logger.info("Inserting/updating embeddings in database...")
count = 0
for (id_, code, description), vector in zip(ids, embeddings):
    vector_bytes = vector.astype(np.float32).tobytes()
    cursor.execute("""
        MERGE INTO embeddings_products tgt
        USING (SELECT :id AS id FROM dual) src
        ON (tgt.id = src.id)
        WHEN MATCHED THEN
            UPDATE SET code = :code, description = :description, vector = :vector
        WHEN NOT MATCHED THEN
            INSERT (id, code, description, vector)
            VALUES (:id, :code, :description, :vector)
    """, {
        "id": id_,
        "code": code,
        "description": description,
        "vector": vector_bytes
    })

connection.commit()
logger.info(f"✅ Successfully inserted/updated {len(ids)} embeddings")

cursor.close()
connection.close()
logger.info("Database connection closed")

print("All Vectors saved with success in Oracle Database.")
logger.info("="*60)
logger.info("Vector processing completed successfully")
logger.info("="*60)