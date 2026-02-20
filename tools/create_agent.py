import os
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FileSearchTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

STATE_DIR = Path(".foundry")
STATE_DIR.mkdir(exist_ok=True)

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

    # Must match what you used for vector stores
    openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-05-01-preview")

    # This is exported by publish_to_vector_store.py via GITHUB_ENV
    vector_store_id = os.getenv("VECTOR_STORE_ID")
    if not vector_store_id:
        raise ValueError(
            "Missing env var: VECTOR_STORE_ID (string). "
            "Ensure publish_to_vector_store.py ran and exported it in the same job."
        )

    agent_name = os.getenv("FOUNDRY_AGENT_NAME", "azure-api-parity-agent")

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

    # If we already created a version this run or earlier, we can reuse it
    state = load_json(AGENT_STATE_FILE)
    existing_name = state.get("agent_name")
    existing_version = state.get("version")

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # Create a new agent version (idempotent strategy: reuse if already recorded locally)
    if existing_name == agent_name and existing_version:
        print(f"Reusing existing agent version from state: {agent_name} v{existing_version}")
        print("Vector store:", vector_store_id)
        print("Model deployment:", model_deployment)
        print("OPENAI_API_VERSION:", openai_api_version)
        return

    definition = PromptAgentDefinition(
        model=model_deployment,
        instructions=instructions,
        tools=[FileSearchTool(vector_store_ids=[vector_store_id])],
    )

    agent_version = project_client.agents.create_version(
        agent_name=agent_name,
        definition=definition,
        description="Azure ARM API parity agent (file search over parity outputs).",
    )

    save_json(
        AGENT_STATE_FILE,
        {
            "agent_id": agent_version.id,
            "agent_name": agent_version.name,
            "version": agent_version.version,
        },
    )

    print(f"✅ Agent created (id: {agent_version.id}, name: {agent_version.name}, version: {agent_version.version})")
    print("Vector store:", vector_store_id)
    print("Model deployment:", model_deployment)
    print("OPENAI_API_VERSION:", openai_api_version)


if __name__ == "__main__":
    main()