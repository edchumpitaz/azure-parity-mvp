import os
import json
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

STATE_DIR = Path(".foundry")
AGENT_STATE_FILE = STATE_DIR / "agent.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError("Missing env var: FOUNDRY_PROJECT_ENDPOINT (string)")

    agent_id = load_json(AGENT_STATE_FILE).get("agent_id")
    if not agent_id:
        raise ValueError("Missing agent_id in .foundry/agent.json. Run create_agent.py first.")

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)
    agents_client = project_client.agents

    # Create a thread, ask a question, run the agent, print output
    thread = agents_client.create_thread()

    question = "What is the lag for virtualMachines? Answer only using parity outputs and cite sources."
    agents_client.create_message(thread_id=thread.id, role="user", content=question)

    run = agents_client.create_and_process_run(thread_id=thread.id, agent_id=agent_id)

    if run.status != "completed":
        raise RuntimeError(f"Run not completed. status={run.status}")

    messages = agents_client.list_messages(thread_id=thread.id)
    # Print latest assistant message
    for m in messages.data:
        if m.role == "assistant":
            print("----- ASSISTANT RESPONSE -----")
            print(m.content[0].text.value if m.content else "")
            break


if __name__ == "__main__":
    main()