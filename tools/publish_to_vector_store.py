import os
import glob
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# ----------------------------
# Config
# ----------------------------
# Environment variables you should set:
#   FOUNDRY_PROJECT_ENDPOINT  (example: https://<your-project>.<region>.api.azureml.ms)
#   VECTOR_STORE_NAME         (optional; default: azure-parity-output)
#
# Files uploaded:
#   output/*.parity.json
#   output/*.parity.md
#
# Output:
#   .foundry/vector_store.json  (dictionary)
# ----------------------------

OUTPUT_DIR = Path("output")
STATE_DIR = Path(".foundry")
STATE_DIR.mkdir(exist_ok=True)

VECTOR_STORE_STATE_FILE = STATE_DIR / "vector_store.json"


def load_state() -> dict:
    if VECTOR_STORE_STATE_FILE.exists():
        return json.loads(VECTOR_STORE_STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    VECTOR_STORE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_parity_files() -> list[Path]:
    patterns = [
        str(OUTPUT_DIR / "*.parity.json"),
        str(OUTPUT_DIR / "*.parity.md"),
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(Path(p).resolve() for p in glob.glob(pat))

    # Only keep real files
    files = [f for f in files if f.exists() and f.is_file()]

    # Sort for deterministic runs
    files.sort(key=lambda p: p.name.lower())
    return files


def main():
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError(
            "Missing env var: FOUNDRY_PROJECT_ENDPOINT (string). "
            "Set it to your Azure AI Foundry project endpoint."
        )

    vector_store_name = os.getenv("VECTOR_STORE_NAME", "azure-parity-output")

    parity_files = get_parity_files()
    if not parity_files:
        raise FileNotFoundError(
            "No parity output files found. Expected files like:\n"
            "  output/*.parity.json\n"
            "  output/*.parity.md\n"
            "Run your parity pipeline first so 'output/' is populated."
        )

    print(f"Found {len(parity_files)} parity files to upload:")
    for f in parity_files:
        print(f"  - {f}")

    # Auth works locally (az login) and in GitHub Actions (OIDC) if configured
    credential = DefaultAzureCredential()

    # Connect to Foundry Project
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # The Foundry docs pattern: get an OpenAI-compatible client
    openai_client = project_client.get_openai_client()

    # State so we reuse the same vector store
    state = load_state()
    vector_store_id = state.get("vector_store_id")

    # Create or reuse vector store
    if not vector_store_id:
        print(f"Creating vector store: {vector_store_name}")
        vs = openai_client.vector_stores.create(name=vector_store_name)
        vector_store_id = vs.id
        state["vector_store_id"] = vector_store_id
        save_state(state)
        print(f"Created vector store id: {vector_store_id}")
    else:
        print(f"Reusing vector store id from state: {vector_store_id}")

    # Upload files and poll until ingestion is complete
    print("Uploading files to vector store and waiting for ingestion...")
    with_files = [open(str(p), "rb") for p in parity_files]
    try:
        batch = openai_client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id,
            files=with_files,
        )
    finally:
        for fh in with_files:
            try:
                fh.close()
            except Exception:
                pass

    print(f"Upload batch status: {batch.status}")
    if getattr(batch, "file_counts", None):
        print(f"File counts: {batch.file_counts}")

    if batch.status != "completed":
        raise RuntimeError(
            f"Vector store ingestion did not complete successfully. Status={batch.status}"
        )

    print("✅ Vector store updated successfully.")
    print(f"Vector store id: {vector_store_id}")
    print(f"State written to: {VECTOR_STORE_STATE_FILE}")


if __name__ == "__main__":
    main()