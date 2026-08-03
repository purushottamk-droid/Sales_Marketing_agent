import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Support both:
#   python main.py
#   python -m marketing_growth_agent.main
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

load_dotenv()

# Default to the same Google Cloud project used by the BigQuery collector.
# Values explicitly supplied in .env or the shell always take precedence.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault(
    "GOOGLE_CLOUD_PROJECT",
    os.getenv("MARKETING_GCP_PROJECT_ID", "atgeir-moae-dev"),
)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

# Import after loading .env because data-source settings are read at import time.
from marketing_growth_agent.scripts.SequentialAgent import root_agent
from marketing_growth_agent.scripts.data_collection_agent import DataCollectionAgent
from marketing_growth_agent.scripts.reporting import build_campaign_wise_report


async def run(data_path: Optional[str] = None) -> dict:
    runner = InMemoryRunner(agent=root_agent, app_name="marketing_growth_agent")
    state = {}
    configured_path = data_path or os.getenv("MARKETING_DATA_PATH")
    if configured_path:
        candidate = Path(configured_path)
        if not candidate.is_absolute() and not candidate.exists():
            candidate = Path(__file__).parent.parent / candidate
        state["marketing_data_path"] = str(candidate.resolve())
    session = await runner.session_service.create_session(
        app_name="marketing_growth_agent", user_id="marketing_manager", state=state
    )

    verbose = os.getenv("MARKETING_VERBOSE_AGENT_OUTPUT", "true").casefold() in {
        "1", "true", "yes", "on"
    }
    async for event in runner.run_async(
        user_id="marketing_manager",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Analyze growth")]),
    ):
        print(f"[DEBUG] event.author={event.author!r} has_content={event.content is not None} parts={len(event.content.parts) if event.content and event.content.parts else 0}")
        if verbose:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        print(f"[{event.author}] {part.text}")
            state_delta = (
                getattr(getattr(event, "actions", None), "state_delta", None) or {}
            )
            if event.author == "data_collection_agent" and "marketing_payload" in state_delta:
                print(
                    "[data_collection_agent] "
                    + json.dumps(state_delta["marketing_payload"], indent=2, default=str)
                )
            if event.author == "decision_action_agent":
                print(f"[decision_action_agent] finish_reason={getattr(event, 'finish_reason', None)} error={getattr(event, 'error_message', None)}")
                if state_delta:
                    print(
                        "[decision_action_agent] state_delta: "
                        + json.dumps(state_delta, indent=2, default=str)
                    )
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        func_call = getattr(part, "function_call", None)
                        if func_call:
                            print(
                                f"[decision_action_agent] called tool: "
                                f"{func_call.name}({json.dumps(dict(func_call.args), default=str)})"
                            )
                        func_response = getattr(part, "function_response", None)
                        if func_response:
                            print(
                                f"[decision_action_agent] tool result: "
                                f"{json.dumps(func_response.response, indent=2, default=str)}"
                            )

    completed = await runner.session_service.get_session(
        app_name="marketing_growth_agent",
        user_id="marketing_manager",
        session_id=session.id,
    )
    result = build_campaign_wise_report(completed.state)
    print("[combined_campaign_report]")
    print(json.dumps(result, indent=2, default=str))
    return result


async def run_data_collection() -> dict:
    """Run only the data collector for BigQuery/Salesforce integration testing."""
    agent = DataCollectionAgent(name="data_collection_agent")
    runner = InMemoryRunner(
        agent=agent,
        app_name="marketing_data_collection_test",
    )
    session = await runner.session_service.create_session(
        app_name="marketing_data_collection_test",
        user_id="marketing_data_tester",
        state={},
    )
    async for _ in runner.run_async(
        user_id="marketing_data_tester",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Collect marketing data")],
        ),
    ):
        pass
    completed = await runner.session_service.get_session(
        app_name="marketing_data_collection_test",
        user_id="marketing_data_tester",
        session_id=session.id,
    )
    crm = completed.state.get("crm_funnel_details", {})
    payload = completed.state.get("marketing_payload", {})
    dataset = completed.state.get("marketing_dataset", {})
    ad_performance = completed.state.get("ad_platform_performance", {})
    summary = {
        "salesforce_status": payload.get("salesforce_status"),
        "salesforce": crm.get("summary", {}),
        "ad_platform_records": ad_performance.get("totals", {}),
        "normalized_campaigns": len(dataset.get("campaigns", [])),
        "source_errors": payload.get("source_errors", {}),
    }
    print("[data_collection_summary]")
    print(json.dumps(summary, indent=2, default=str))
    result = {
        "marketing_payload": payload,
        "crm_funnel_details": crm,
        "ad_platform_performance": ad_performance,
        "marketing_dataset": dataset,
    }
    print("[data_collection_agent]")
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the marketing growth pipeline")
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Run only the data collection agent; skip LLM agents and email.",
    )
    arguments = parser.parse_args()
    try:
        if arguments.data_only:
            asyncio.run(run_data_collection())
        else:
            asyncio.run(run())
    except Exception as exc:
        from google.auth.exceptions import DefaultCredentialsError

        if isinstance(exc, DefaultCredentialsError):
            raise SystemExit(
                "\nGoogle Cloud authentication is required for BigQuery and "
                "Vertex AI.\n\n"
                "1. Install the Google Cloud CLI.\n"
                "2. Run: gcloud auth application-default login\n"
                "3. Run: gcloud config set project atgeir-moae-dev\n"
                "4. Retry: python main.py\n\n"
                "Alternatively, set GOOGLE_APPLICATION_CREDENTIALS to an "
                "authorized service-account JSON file."
            ) from None
        raise
