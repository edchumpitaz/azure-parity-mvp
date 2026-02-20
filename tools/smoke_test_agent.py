import os
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

STATE_DIR = Path(".foundry")
AGENT_STATE_FILE = STATE_DIR / "agent.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def extract_text(resp) -> str:
    # openai>=2.x responses API shape can vary slightly; handle common cases
    if hasattr(resp, "output_text") and resp.output_text:
        return resp.output_text

    # Fallback: walk output items
    parts = []
    out = getattr(resp, "output", None) or []
    for item in out:
        content = getattr(item, "content", None) or []
        for c in content:
            t = getattr(c, "text", None)
            if t and hasattr(t, "value"):
                parts.append(t.value)
            elif hasattr(c, "text") and isinstance(c.text, str):
                parts.append(c.text)
    return "\n".join(parts).strip()


def main():
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError("Missing env var: FOUNDRY_PROJECT_ENDPOINT (string)")

    # Exported by publish_to_vector_store.py via GITHUB_ENV
    vector_store_id = os.getenv("VECTOR_STORE_ID")
    if not vector_store_id:
        raise ValueError("Missing env var: VECTOR_STORE_ID (string). Ensure publish step ran in same job.")

    # Model deployment name is needed to run a response
    model_deployment = os.getenv("MODEL_DEPLOYMENT_NAME")
    if not model_deployment:
        # Try to fall back to state (if you stored it), otherwise require env var
        state = load_json(AGENT_STATE_FILE)
        model_deployment = state.get("model_deployment")
    if not model_deployment:
        raise ValueError("Missing env var: MODEL_DEPLOYMENT_NAME (string) for smoke test.")

    question = "What is the lag for virtualMachines? Answer only using parity outputs and cite sources."

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # OpenAI-compatible client bound to Foundry project
    openai_client = project_client.get_openai_client(api_version=os.getenv("OPENAI_API_VERSION", "2024-05-01-preview"))

    print("Vector store:", vector_store_id)
    print("Model deployment:", model_deployment)
    print("Question:", question)

    resp = openai_client.responses.create(
        model=model_deployment,
        input=question,
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [vector_store_id],
            }
        ],
    )

    print("----- ASSISTANT RESPONSE -----")
    print(extract_text(resp) or str(resp))


if __name__ == "__main__":
    main()