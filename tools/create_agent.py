import os
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import FileSearchTool

STATE_DIR = Path(".foundry")
STATE_DIR.mkdir(exist_ok=True)

VECTOR_STORE_STATE_FILE = STATE_DIR / "vector_store.json"
AGENT_STATE_FILE = STATE_DIR / "agent.json"


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError("Missing env var: FOUNDRY_PROJECT_ENDPOINT (string)")

    model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")
    if not model_deployment:
        raise ValueError("Missing env var: MODEL_DEPLOYMENT_NAME (string)")

    openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-05-01-preview")

    vs_state = load_json(VECTOR_STORE_STATE_FILE)
    vector_store_id = vs_state.get("vector_store_id")
    if not vector_store_id:
        raise ValueError(
            f"Missing vector_store_id in {VECTOR_STORE_STATE_FILE}. "
            "Run publish_to_vector_store.py first."
        )

    instructions = """You are the Azure ARM API Parity Analyst for Azure Public vs Azure US Government.

Source of truth:
- Use ONLY the retrieved parity artifacts (parity JSON/Markdown) available via file search.
- Do NOT infer feature availability from api-version presence. API lag is a signal, not proof.

Grounding rules:
- If you cannot find the answer in retrieved content, say you cannot determine from the parity outputs.
- Always cite the retrieved sources that support your answer.

Answer format:
- For a specific resourceType: give status (Aligned/PublicAhead/GovAhead), lagDaysPublicAhead, missingInGov, missingInPublic (if present), then citations.
- For “largest gap/top N” questions: rely on lagDays and missing counts from retrieved artifacts; if not available, explain the limitation and cite what you used.
"""

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # Create agent with File Search bound to the vector store
    agents_client = project_client.agents

    # Reuse if already created
    agent_state = load_json(AGENT_STATE_FILE)
    agent_id = agent_state.get("agent_id")

    if not agent_id:
        agent = agents_client.create_agent(
            model=model_deployment,
            name="azure-api-parity-agent",
            instructions=instructions,
            tools=[FileSearchTool(vector_store_ids=[vector_store_id])],
            # pass api version through openai-compatible stack via env var
        )
        agent_id = agent.id
        save_json(AGENT_STATE_FILE, {"agent_id": agent_id})
        print(f"✅ Created agent: {agent_id}")
    else:
        print(f"Reusing existing agent_id from state: {agent_id}")

    print("Vector store:", vector_store_id)
    print("Model deployment:", model_deployment)
    print("OPENAI_API_VERSION:", openai_api_version)


if __name__ == "__main__":
    main()