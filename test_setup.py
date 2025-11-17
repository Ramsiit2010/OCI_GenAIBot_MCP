"""
Environment setup test for the current OCI GenAI Bot.
Validates packages, files, config, wallet, DB connection, and embeddings table.
"""

import sys
import os
from typing import Dict, Tuple


def test_imports() -> bool:
    """Test if required packages are installed (no Flask)."""
    print("=" * 60)
    print("Testing Package Imports...")
    print("=" * 60)

    required = [
        ("langchain_core", "LangChain Core"),
        ("langchain_community", "LangChain Community"),
        ("langgraph", "LangGraph"),
        ("mcp", "MCP"),
        ("oracledb", "Oracle DB"),
        ("oci", "OCI SDK"),
        ("rapidfuzz", "RapidFuzz"),
        ("phoenix", "Arize Phoenix"),
    ]
    optional = [
        ("gradio", "Gradio (optional)")
    ]

    all_ok = True
    for package, name in required + optional:
        try:
            __import__(package)
            print(f"✅ {name}")
        except ImportError as e:
            marker = "❌" if (package, name) in required else "⚠️"
            print(f"{marker} {name} - {e}")
            if (package, name) in required:
                all_ok = False

    # Verify langgraph prebuilt API presence
    try:
        from langgraph.prebuilt import create_react_agent  # noqa: F401
        print("✅ LangGraph prebuilt.create_react_agent available")
    except Exception as e:
        print(f"❌ LangGraph prebuilt.create_react_agent import failed: {e}")
        all_ok = False

    return all_ok


def test_files() -> bool:
    """Test if core files exist (no Flask artifacts)."""
    print("\n" + "=" * 60)
    print("Testing File Structure...")
    print("=" * 60)

    required_files = [
        "main.py",
        "server_invoice_items.py",
        "product_search.py",
        "process_vector_products.py",
        "requirements.txt",
        "config.properties",
        "Wallet_ItsmyATPVectorDBs",
    ]
    optional_files = [
        "gradio_app.py",
    ]

    all_ok = True
    for path in required_files:
        if os.path.exists(path):
            print(f"✅ {path}")
        else:
            print(f"❌ {path} - NOT FOUND")
            all_ok = False

    for path in optional_files:
        if os.path.exists(path):
            print(f"✅ {path} (optional)")
        else:
            print(f"ℹ️ {path} not found (optional)")

    # Guard: ensure no stale Flask structure
    stale = ["app.py", "templates", "static"]
    for path in stale:
        if os.path.exists(path):
            print(f"⚠️ Stale Flask artifact present: {path}")

    return all_ok


def load_properties() -> Tuple[bool, Dict[str, str]]:
    print("\n" + "=" * 60)
    print("Reading config.properties...")
    print("=" * 60)
    try:
        from config_loader import load_properties as _load
        props = _load()
        if not props:
            print("❌ config.properties is missing or empty")
            return False, {}

        required_keys = [
            "OCI_GENAI_MODEL_ID",
            "OCI_GENAI_EMBEDDING_MODEL_ID",
            "OCI_GENAI_ENDPOINT",
            "OCI_COMPARTMENT_OCID",
            "WALLET_PATH",
            "DB_ALIAS",
            "USERNAME",
            "PASSWORD",
        ]
        ok = True
        for k in required_keys:
            if props.get(k):
                if k == "PASSWORD":
                    print(f"✅ {k}=********")
                else:
                    print(f"✅ {k}={props.get(k)}")
            else:
                print(f"❌ {k} is missing in config.properties")
                ok = False

        # Quick sanity for embedding model id
        emb_id = props.get("OCI_GENAI_EMBEDDING_MODEL_ID", "")
        if emb_id and "embed" not in emb_id.lower():
            print(f"⚠️ Embedding model id '{emb_id}' doesn't look like an embed model")

        return ok, props
    except Exception as e:
        print(f"❌ Failed to read config.properties: {e}")
        return False, {}


def test_wallet(props: Dict[str, str]) -> bool:
    """Test if wallet directory and essential files exist."""
    print("\n" + "=" * 60)
    print("Testing Oracle Wallet...")
    print("=" * 60)

    wallet_dir = props.get("WALLET_PATH", "Wallet_ItsmyATPVectorDBs")
    required_wallet_files = [
        "cwallet.sso",
        "tnsnames.ora",
        "sqlnet.ora",
    ]

    if not os.path.exists(wallet_dir):
        print(f"❌ Wallet directory '{wallet_dir}' not found")
        return False

    all_ok = True
    for file in required_wallet_files:
        full_path = os.path.join(wallet_dir, file)
        if os.path.exists(full_path):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - NOT FOUND")
            all_ok = False

    return all_ok


def test_database_connection(props: Dict[str, str]) -> bool:
    """Test database connection using wallet and credentials from config."""
    print("\n" + "=" * 60)
    print("Testing Database Connection...")
    print("=" * 60)

    try:
        import oracledb
        from config_loader import apply_db_env

        apply_db_env(props)

        wallet = props.get("WALLET_PATH")
        if wallet:
            os.environ["TNS_ADMIN"] = wallet

        user = props.get("USERNAME")
        password = props.get("PASSWORD")
        dsn = props.get("DB_ALIAS")

        connection = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=wallet if wallet else None,
            wallet_location=wallet if wallet else None,
            wallet_password=password,
        )

        cursor = connection.cursor()
        cursor.execute("SELECT 1 FROM dual")
        cursor.fetchone()
        print("✅ Database connection successful")

        cursor.close()
        connection.close()
        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def test_embeddings_table(props: Dict[str, str]) -> bool:
    """Test if embeddings table exists and has data."""
    print("\n" + "=" * 60)
    print("Testing Embeddings Table...")
    print("=" * 60)

    try:
        import oracledb

        wallet = props.get("WALLET_PATH")
        if wallet:
            os.environ["TNS_ADMIN"] = wallet

        connection = oracledb.connect(
            user=props.get("USERNAME"),
            password=props.get("PASSWORD"),
            dsn=props.get("DB_ALIAS"),
            config_dir=wallet if wallet else None,
            wallet_location=wallet if wallet else None,
            wallet_password=props.get("PASSWORD"),
        )
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM embeddings_products")
        count = cursor.fetchone()[0]
        cursor.close()
        connection.close()

        if count > 0:
            print(f"✅ embeddings_products has {count} records")
            return True
        else:
            print("⚠️ embeddings_products table is empty")
            print("   Run: python process_vector_products.py")
            return False

    except Exception as e:
        print(f"❌ Embeddings table check failed: {e}")
        print("   Run: python process_vector_products.py")
        return False


def main() -> int:
    print("\n")
    print("🔍 OCI GenAI Bot - Environment Test")
    print("=" * 60)

    results = []

    # Packages
    results.append(("Package Imports", test_imports()))

    # Files
    results.append(("File Structure", test_files()))

    # Config
    cfg_ok, props = load_properties()
    results.append(("Config Properties", cfg_ok))

    # Wallet
    if cfg_ok:
        results.append(("Oracle Wallet", test_wallet(props)))
    else:
        results.append(("Oracle Wallet", False))

    # DB connection
    if cfg_ok:
        results.append(("Database Connection", test_database_connection(props)))
    else:
        results.append(("Database Connection", False))

    # Embeddings table
    if cfg_ok:
        results.append(("Embeddings Table", test_embeddings_table(props)))
    else:
        results.append(("Embeddings Table", False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if not result:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✅ All tests passed! You're ready to run.")
        print("\nNext steps:")
        print("1. python main.py                 # Start CLI with Phoenix")
        if os.path.exists("gradio_app.py"):
            print("2. python gradio_app.py          # Start web UI (optional)")
        print("3. Open http://localhost:6006    # Phoenix dashboard")
    else:
        print("\n❌ Some tests failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("1. pip install -r requirements.txt  # Install missing packages")
        print("2. Update config.properties          # Check OCI/DB settings")
        print("3. python process_vector_products.py # Generate embeddings")

    print("\n")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
