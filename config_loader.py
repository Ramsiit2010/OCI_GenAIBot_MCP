"""
Shared configuration loader for OCI GenAI Bot.
Reads config.properties, writes OCI SDK config, and applies DB env variables.
"""
import os
import re
from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def load_properties(file_path: str = None) -> Dict[str, str]:
    file_path = file_path or str(Path(os.getcwd()) / 'config.properties')
    cfg: Dict[str, str] = {}
    if not os.path.exists(file_path):
        logger.warning("config.properties not found at %s", file_path)
        return cfg
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                cfg[k] = v
    return cfg


def ensure_oci_config(props: Dict[str, str]) -> None:
    user = props.get('OCI_USER')
    fingerprint = props.get('OCI_FINGERPRINT')
    key_file = props.get('OCI_KEY_FILE')
    tenancy = props.get('OCI_TENANCY_OCID') or props.get('OCI_COMPARTMENT_OCID')
    endpoint = props.get('OCI_GENAI_ENDPOINT', '')

    if not (user and fingerprint and key_file and tenancy):
        logger.warning("Missing OCI credentials in config.properties (user/fingerprint/key_file/tenancy). Using existing OCI setup if available.")
        return

    m = re.search(r"generativeai\.(.*?)\.oci\.oraclecloud\.com", endpoint)
    region = m.group(1) if m else os.getenv('OCI_REGION', 'us-chicago-1')

    root = Path(os.getcwd())
    key_path = str((root / key_file).resolve())
    oci_dir = root / '.oci'
    oci_dir.mkdir(exist_ok=True)
    config_path = oci_dir / 'config'
    content = (
        "[DEFAULT]\n"
        f"user={user}\n"
        f"fingerprint={fingerprint}\n"
        f"key_file={key_path}\n"
        f"tenancy={tenancy}\n"
        f"region={region}\n"
    )
    config_path.write_text(content, encoding='utf-8')
    os.environ['OCI_CONFIG_FILE'] = str(config_path)
    os.environ['OCI_CLI_PROFILE'] = 'DEFAULT'
    logger.info("OCI SDK config written to %s (region=%s)", config_path, region)


def apply_db_env(props: Dict[str, str]) -> None:
    wallet = props.get('WALLET_PATH')
    if wallet:
        wallet_path = str((Path(os.getcwd()) / wallet).resolve())
        os.environ['TNS_ADMIN'] = wallet_path
        logger.info("TNS_ADMIN set to %s", wallet_path)
    if props.get('USERNAME'):
        os.environ['DB_USERNAME'] = props['USERNAME']
    if props.get('PASSWORD'):
        os.environ['DB_PASSWORD'] = props['PASSWORD']
    if props.get('DB_ALIAS'):
        os.environ['DB_ALIAS'] = props['DB_ALIAS']


def get_oci_llm_params(props: Dict[str, str]) -> Dict[str, str]:
    return {
        'model_id': props.get('OCI_GENAI_MODEL_ID', 'cohere.embed-multilingual-v3.0'),
        'service_endpoint': props.get('OCI_GENAI_ENDPOINT', 'https://inference.generativeai.us-chicago-1.oci.oraclecloud.com'),
        'compartment_id': props.get('OCI_COMPARTMENT_OCID'),
    }
