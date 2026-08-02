import os
import sys
from pathlib import Path

# Make the outer package (marketing_growth_agent) importable, since some
# internal modules (e.g. data_collection_agent/agent.py) import from
# marketing_growth_agent.dto.models using the fully-qualified package name.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("MARKETING_GCP_PROJECT_ID", "atgeir-moae-dev")
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"

import json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from marketing_growth_agent.scripts.SequentialAgent import root_agent

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

api = FastAPI(title="Marketing Growth Agent — SSE API")

api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],  # Update with your frontend URLs in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name="marketing_growth_agent",
    session_service=session_service,
)


# ─────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    user_id: str
    # Optional overrides — all fall back to .env defaults if omitted.
    marketing_data_path: str | None = None
    lookback_days: int | None = None
    pipeline_target: float | None = None
    default_target_cpl: float | None = None


class RunRequest(BaseModel):
    user_id: str
    session_id: str


# ─────────────────────────────────────────────
# Helper — SSE formatter
# ─────────────────────────────────────────────

def sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


async def stream_events(event_gen, user_id, session_id):
    """Stream all agent events as SSE, ending with the complete state."""
    last_author = "data_collection_agent"
    try:
        async for event in event_gen:
            text = ""
            if event.content and event.content.parts:
                text = "".join(
                    p.text for p in event.content.parts
                    if hasattr(p, "text") and p.text
                )

            tool_calls = []
            tool_results = []
            if event.content and event.content.parts:
                for part in event.content.parts:
                    func_call = getattr(part, "function_call", None)
                    if func_call:
                        tool_calls.append({
                            "name": func_call.name,
                            "args": dict(func_call.args) if func_call.args else {},
                        })
                    func_response = getattr(part, "function_response", None)
                    if func_response:
                        tool_results.append({
                            "name": func_response.name,
                            "response": func_response.response,
                        })

            last_author = event.author

            yield sse("progress", {
                "author": event.author,
                "id": event.id,
                "text": text,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            })

        # Loop finished — state is now safely committed.
        session = await runner.session_service.get_session(
            app_name="marketing_growth_agent",
            user_id=user_id,
            session_id=session_id,
        )

        marketing_dataset = session.state.get("marketing_dataset") if session else None
        marketing_payload = session.state.get("marketing_payload") if session else None
        campaign_analysis_results = session.state.get("campaign_analysis_results") if session else None
        growth_assessment_result = session.state.get("growth_assessment_result") if session else None

        decision_action_results_raw = session.state.get("decision_action_results") if session else None
        try:
            decision_action_results = json.loads(decision_action_results_raw) if decision_action_results_raw else None
        except (TypeError, json.JSONDecodeError):
            decision_action_results = decision_action_results_raw  # fall back to raw string

        yield sse("done", {
            "author": last_author,
            "text": "",
            "marketing_dataset": marketing_dataset,
            "marketing_payload": marketing_payload,
            "campaign_analysis_results": campaign_analysis_results,
            "growth_assessment_result": growth_assessment_result,
            "decision_action_results": decision_action_results,
        })

    except Exception as e:
        import logging
        logging.error(f"Error in stream_events: {str(e)}", exc_info=True)
        yield sse("error", {"message": str(e)})


# ─────────────────────────────────────────────
# ENDPOINT 1 — Health check
# ─────────────────────────────────────────────

@api.get("/health")
async def healthz():
    return {"status": "ok"}


# ─────────────────────────────────────────────
# ENDPOINT 2 — Create a session
# ─────────────────────────────────────────────

@api.post("/agent/sessions")
async def create_session(req: CreateSessionRequest):
    """Creates a fresh session for the marketing growth pipeline."""
    state = {}
    if req.marketing_data_path:
        state["marketing_data_path"] = req.marketing_data_path
    if req.lookback_days is not None:
        state["lookback_days"] = req.lookback_days
    if req.pipeline_target is not None:
        state["pipeline_target"] = req.pipeline_target
    if req.default_target_cpl is not None:
        state["default_target_cpl"] = req.default_target_cpl

    session = await session_service.create_session(
        app_name="marketing_growth_agent",
        user_id=req.user_id,
        state=state,
    )
    return {
        "session_id": session.id,
        "user_id": req.user_id,
        "initial_state": session.state,
    }


# ─────────────────────────────────────────────
# ENDPOINT 3 — Run the full pipeline
# ─────────────────────────────────────────────

@api.post("/agent/run")
async def run_agent(req: RunRequest):
    """
    Runs the marketing growth pipeline and streams live progress.
    The final 'done' event contains marketing_dataset, marketing_payload,
    campaign_analysis_results, and growth_assessment_result.
    Note: decision_action_agent has no output_key — its email-send
    results appear only as tool_calls/tool_results in progress events,
    not in the final 'done' payload.
    """
    content = types.Content(role="user", parts=[types.Part(text="Analyze growth")])

    event_gen = runner.run_async(
        user_id=req.user_id,
        session_id=req.session_id,
        new_message=content,
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    )

    return StreamingResponse(
        stream_events(event_gen, req.user_id, req.session_id),
        media_type="text/event-stream"
    )


# ─────────────────────────────────────────────
# ENDPOINT 4 — Get final pipeline result
# ─────────────────────────────────────────────

@api.get("/agent/result/{session_id}")
async def get_result(session_id: str, user_id: str):
    """
    Returns the final marketing pipeline state.
    Call this AFTER you receive event: done from /agent/run.
    """
    session = await session_service.get_session(
        app_name="marketing_growth_agent",
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    raw = session.state.get("decision_action_results")
    try:
        decision_action_results = json.loads(raw) if raw else None
    except (TypeError, json.JSONDecodeError):
        decision_action_results = raw

    return {
        "session_id": session_id,
        "marketing_dataset": session.state.get("marketing_dataset"),
        "marketing_payload": session.state.get("marketing_payload"),
        "campaign_analysis_results": session.state.get("campaign_analysis_results"),
        "growth_assessment_result": session.state.get("growth_assessment_result"),
        "decision_action_results": decision_action_results,
    }