import os
import sys
import logging
from pathlib import Path
from datetime import datetime
import oracledb
import zipfile
import numpy as np
import difflib
from rapidfuzz import fuzz
from langchain_community.embeddings import OCIGenAIEmbeddings
from config_loader import load_properties, ensure_oci_config, apply_db_env, get_oci_llm_params

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

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


class SearchSimilarProduct:
    def __init__(
            self,
            top_k=5,
            minimal_distance=1.0,
            model_id=None,
            service_endpoint=None,
            compartment_id=None,
            auth_profile="DEFAULT",
            wallet_path=None,
            db_alias=None,
            username=None,
            password=None
    ):
        logger.info("Initializing SearchSimilarProduct...")

        # Load config and apply envs on first use
        PROPS = load_properties(str(Path(os.getcwd())/ 'config.properties'))
        ensure_oci_config(PROPS)
        apply_db_env(PROPS)

        # Pull settings from config when not provided
        if wallet_path is None:
            wallet_path = str((Path(os.getcwd()) / PROPS.get('WALLET_PATH', 'Wallet_ItsmyATPVectorDBs')).resolve())
        if db_alias is None:
            db_alias = PROPS.get('DB_ALIAS', 'itsmyatpvectordb_high')
        if username is None:
            username = PROPS.get('USERNAME', 'ADMIN')
        if password is None:
            password = PROPS.get('PASSWORD', '')

        os.environ["TNS_ADMIN"] = wallet_path
        try:
            self.conn = oracledb.connect(
                user=username,
                password=password,
                dsn=db_alias,
                config_dir=wallet_path,
                wallet_location=wallet_path,
                wallet_password=password
            )
            logger.info("✅ Database connection established")
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}", exc_info=True)
            raise
            
        self.top_k = top_k
        self.minimal_distance = minimal_distance

        try:
            if model_id is None or service_endpoint is None or compartment_id is None:
                llm = get_oci_llm_params(PROPS)
                # Use separate embedding model, not the chat model!
                model_id = PROPS.get('OCI_GENAI_EMBEDDING_MODEL_ID', 'cohere.embed-multilingual-v3.0')
                service_endpoint = llm['service_endpoint']
                compartment_id = llm['compartment_id']
            self.embedding = OCIGenAIEmbeddings(
                model_id=model_id,
                service_endpoint=service_endpoint,
                compartment_id=compartment_id,
                auth_profile=auth_profile
            )
            logger.info(f"✅ OCI GenAI Embeddings initialized (model: {model_id})")
        except Exception as e:
            logger.error(f"❌ Failed to initialize embeddings: {e}", exc_info=True)
            raise

        logger.info("📦 Loading Oracle Vectors...")
        print("📦 Loading Oracle Vectors...")
        self._load_embeddings()

    def _load_embeddings(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, code, description, vector FROM embeddings_products")
            self.vectors = []
            self.products = []
            for row in cursor.fetchall():
                id_, code, description, blob = row
                vector = np.frombuffer(blob.read(), dtype=np.float32)
                self.vectors.append(vector)
                self.products.append({
                    "id": id_,
                    "code": code,
                    "description": description
                })
            self.vectors = np.array(self.vectors)
            logger.info(f"✅ Loaded {len(self.products)} product embeddings")
        except Exception as e:
            logger.error(f"❌ Failed to load embeddings: {e}", exc_info=True)
            raise

    def _correct_input(self, input_user):
        descriptions = [p["description"] for p in self.products]
        suggestions = difflib.get_close_matches(input_user, descriptions, n=1, cutoff=0.6)
        return suggestions[0] if suggestions else input_user

    def search_similar_products(self, description_input):
        logger.info(f"Searching for products similar to: {description_input[:50]}...")
        description_input = description_input.strip()
        description_corrected = self._correct_input(description_input)

        if description_corrected != description_input:
            logger.info(f"Input corrected from '{description_input}' to '{description_corrected}'")

        results = {
            "consult_original": description_input,
            "consult_used": description_corrected,
            "semantics": [],
            "fallback_fuzzy": []
        }

        try:
            consult_emb = self.embedding.embed_query(description_corrected)
            consult_emb = np.array(consult_emb)

            # Euclidean distance calculation
            dists = np.linalg.norm(self.vectors - consult_emb, axis=1)
            top_indices = np.argsort(dists)[:self.top_k]

            for idx in top_indices:
                dist = dists[idx]
                if dist < self.minimal_distance:
                    match = self.products[idx]
                    similarity = 1 / (1 + dist)
                    results["semantics"].append({
                        "id": match["id"],
                        "code": match["code"],
                        "description": match["description"],
                        "similarity": round(similarity * 100, 2),
                        "distance": round(dist, 4)
                    })

            logger.info(f"Found {len(results['semantics'])} semantic matches")

            if not results["semantics"]:
                logger.info("No semantic matches found, falling back to fuzzy matching")
                better_fuzz = []
                for product in self.products:
                    score = fuzz.token_sort_ratio(description_corrected, product["description"])
                    better_fuzz.append((product, score))
                better_fuzz.sort(key=lambda x: x[1], reverse=True)

                for product, score in better_fuzz[:self.top_k]:
                    results["fallback_fuzzy"].append({
                        "id": product["id"],
                        "code": product["code"],
                        "description": product["description"],
                        "score_fuzzy": round(score, 2)
                    })
                
                logger.info(f"Found {len(results['fallback_fuzzy'])} fuzzy matches")

        except Exception as e:
            logger.error(f"Error during product search: {e}", exc_info=True)

        return results