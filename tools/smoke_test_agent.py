import os
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

STATE_DIR = Path(".foundry")
AGENT_STATE_FILE = STATE_DIR / "agent.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run create_agent.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError("Missing env var: FOUNDRY_PROJECT_ENDPOINT (string)")

    state = load_json(AGENT_STATE_FILE)
    agent_id = state.get("agent_id")
    agent_name = state.get("agent_name")
    agent_version = state.get("version")

    if not agent_id:
        raise ValueError("Missing agent_id in .foundry/agent.json")

    question = "What is the lag for virtualMachines? Answer only using parity outputs and cite sources."

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # Projects agent runtime (no threads). Method names can vary by prerelease.
    # Try the most common runtime entrypoints.
    agents = project_client.agents

    print(f"Using agent: id={agent_id}, name={agent_name}, version={agent_version}")
    print("Question:", question)

    # Attempt 1: invoke by agent_id (most common)
    if hasattr(agents, "invoke"):
        result = agents.invoke(agent_id=agent_id, input=question)
        print("----- ASSISTANT RESPONSE -----")
        print(result.output if hasattr(result, "output") else result)
        return

    # Attempt 2: run by agent name/version
    if hasattr(agents, "run"):
        result = agents.run(agent_name=agent_name, version=agent_version, input=question)
        print("----- ASSISTANT RESPONSE -----")
        print(result.output if hasattr(result, "output") else result)
        return

    print([m for m in dir(agents) if "run" in m or "invoke" in m or "chat" in m or "conversation" in m])

    # If neither exists, fail with a helpful message
    raise AttributeError(
        "Could not find an agent runtime method. "
        "Expected agents.invoke(...) or agents.run(...). "
        "Print available methods and adjust to your installed azure-ai-projects version."
    )


if __name__ == "__main__":
    main()