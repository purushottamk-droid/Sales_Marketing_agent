"""Salesforce Lead and Opportunity client supporting local and Cloud Run MCP."""

import asyncio
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit


def _tool_payload(result: Any) -> Dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if text:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
    raise RuntimeError("Salesforce MCP tool returned no JSON object")


def _base_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _find_gcloud() -> str:
    configured = os.getenv("GCLOUD_COMMAND", "").strip()
    candidates = [
        configured,
        "gcloud",
        str(
            Path.home()
            / "AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
        ),
    ]
    for candidate in candidates:
        if candidate == "gcloud":
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        elif candidate and Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser())
    return "gcloud"


async def _identity_token(audience: str) -> str:
    """Mint a Cloud Run identity token locally or from deployed credentials."""
    def fetch() -> str:
        gcloud = _find_gcloud()
        errors = []
        for arguments in (
            ["auth", "print-identity-token", f"--audiences={audience}"],
            ["auth", "print-identity-token"],
        ):
            command = [gcloud, *arguments]
            use_shell = False
            if gcloud.casefold().endswith((".cmd", ".bat")):
                command = subprocess.list2cmdline([gcloud, *arguments])
                use_shell = True
            try:
                result = subprocess.run(
                    command,
                    shell=use_shell,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                if result.stderr.strip():
                    errors.append(result.stderr.strip())
            except (FileNotFoundError, subprocess.SubprocessError):
                continue

        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        try:
            return id_token.fetch_id_token(Request(), audience)
        except Exception as exc:
            detail = errors[-1] if errors else str(exc)
            raise RuntimeError(
                "Unable to create a Cloud Run identity token. "
                f"gcloud/credential error: {detail}"
            ) from exc

    return await asyncio.to_thread(fetch)


async def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from mcp import ClientSession

    url = os.getenv(
        "SALESFORCE_MCP_URL",
        os.getenv("MCP_SALESFORCE_SERVER_URL", "http://localhost:8080/mcp"),
    ).strip()
    transport = os.getenv("SALESFORCE_MCP_TRANSPORT", "auto").strip().lower()
    if transport == "auto":
        transport = "sse" if url.rstrip("/").endswith("/sse") else "streamable-http"

    auth_mode = os.getenv("SALESFORCE_MCP_AUTH", "auto").strip().lower()
    if auth_mode == "auto":
        auth_mode = "none" if "localhost" in url or "127.0.0.1" in url else "gcp-iam"
    headers = {}
    if auth_mode == "gcp-iam":
        token = await _identity_token(_base_url(url))
        headers["Authorization"] = f"Bearer {token}"

    if transport == "sse":
        from mcp.client.sse import sse_client

        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)
    elif transport == "streamable-http":
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)
    else:
        raise ValueError("SALESFORCE_MCP_TRANSPORT must be auto, sse, or streamable-http")

    if getattr(result, "isError", False):
        raise RuntimeError(f"Salesforce MCP tool {name} failed: {result.content}")
    return _tool_payload(result)


def _field(record: Dict[str, Any], *names: str) -> Any:
    normalized = {
        "".join(character for character in str(key).casefold() if character.isalnum()): value
        for key, value in record.items()
    }
    for name in names:
        key = "".join(
            character for character in name.casefold() if character.isalnum()
        )
        if key in normalized:
            return normalized[key]
    return None


def _lead(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _field(record, "id", "lead_id"),
        "status": _field(record, "status", "lead_status"),
        "created_date": _field(record, "created_date", "created_date__c", "CreatedDate"),
        "company": _field(record, "company"),
        "title": _field(record, "title", "job_title"),
        "industry": _field(record, "industry"),
        "annual_revenue": _field(record, "annual_revenue", "AnnualRevenue"),
        "number_of_employees": _field(
            record, "number_of_employees", "NumberOfEmployees", "company_size"
        ),
        "lead_source": _field(
            record, "lead_source", "LeadSource", "Original_Source__c"
        ),
        "utm_source": _field(record, "utm_source", "utm_source__c"),
        "utm_campaign": _field(record, "utm_campaign", "utm_campaign__c"),
        "gclid": _field(record, "gclid", "GCLID__c"),
        "converted_opportunity_id": _field(
            record,
            "converted_opportunity_id",
            "converted_opportunity_id__c",
            "ConvertedOpportunityId",
        ),
    }


def _opportunity(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _field(
            record, "id", "opportunity_id", "Opportunity_ID__c", "OpportunityId"
        ),
        "name": _field(record, "name", "opportunity_name"),
        "account_id": _field(record, "account_id", "AccountId"),
        "account_name": _field(record, "account_name"),
        "stage_name": _field(record, "stage_name", "StageName", "current_stage"),
        "amount": _field(record, "amount", "deal_size", "deal_value_arr"),
        "probability": _field(record, "probability"),
        "close_date": _field(
            record, "close_date", "CloseDate", "close_date_target"
        ),
        "lead_source": _field(
            record, "lead_source", "LeadSource", "Opportunity_Source__c"
        ),
        "created_date": _field(record, "created_date", "created_date__c", "CreatedDate"),
        "is_closed": bool(_field(record, "is_closed", "IsClosed")),
        "is_won": bool(_field(record, "is_won", "IsWon")),
    }


def _records(payload: Dict[str, Any], object_name: str) -> List[Dict[str, Any]]:
    candidates = (
        payload.get("records"),
        payload.get(object_name),
        payload.get(object_name.rstrip("s")),
    )
    return next((value for value in candidates if isinstance(value, list)), [])


async def fetch_salesforce_data(
    lookback_days: int, limit: int | None = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch, normalize, and safely join Salesforce Leads and Opportunities."""
    record_limit = limit or int(os.getenv("SALESFORCE_MCP_RECORD_LIMIT", "5000"))
    modified_since = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    mode = os.getenv("SALESFORCE_MCP_ARGUMENT_MODE", "auto").strip().lower()
    url = os.getenv(
        "SALESFORCE_MCP_URL",
        os.getenv("MCP_SALESFORCE_SERVER_URL", "http://localhost:8080/mcp"),
    )
    if mode == "auto":
        mode = "lookback_days" if url.rstrip("/").endswith("/sse") else "modified_since"
    arguments = (
        {"lookback_days": lookback_days}
        if mode == "lookback_days"
        else {"limit": record_limit, "modified_since": modified_since}
    )

    lead_payload, opportunity_payload = await asyncio.gather(
        _call_tool("get_leads", arguments),
        _call_tool("get_opportunities", arguments),
    )
    leads = [_lead(row) for row in _records(lead_payload, "leads")]
    opportunities = [
        _opportunity(row) for row in _records(opportunity_payload, "opportunities")
    ]
    opportunity_by_id = {
        str(row["id"]).strip().upper(): row for row in opportunities if row.get("id")
    }

    funnel = []
    positional_fallback = os.getenv(
        "SALESFORCE_POSITIONAL_JOIN_FALLBACK", "false"
    ).strip().casefold() in {"1", "true", "yes", "on"}
    for index, lead in enumerate(leads):
        opportunity_id = lead.get("converted_opportunity_id")
        opportunity = (
            opportunity_by_id.get(str(opportunity_id).strip().upper(), {})
            if opportunity_id
            else {}
        )
        join_method = "salesforce_id" if opportunity else "unmatched"
        if not opportunity and positional_fallback and index < len(opportunities):
            opportunity = opportunities[index]
            join_method = "position_fallback"
        funnel.append({
            "lead_id": lead.get("id"),
            "lead_status": lead.get("status"),
            "lead_created_date": lead.get("created_date"),
            "company": lead.get("company"),
            "job_title": lead.get("title"),
            "industry": lead.get("industry"),
            "annual_revenue": lead.get("annual_revenue"),
            "company_size": lead.get("number_of_employees"),
            "lead_source": lead.get("lead_source"),
            "utm_source": lead.get("utm_source"),
            "utm_campaign": lead.get("utm_campaign"),
            "gclid": lead.get("gclid"),
            "opportunity_id": opportunity.get("id"),
            "opportunity_name": opportunity.get("name"),
            "opportunity_stage": opportunity.get("stage_name"),
            "deal_size": opportunity.get("amount"),
            "opportunity_probability": opportunity.get("probability"),
            "is_won": opportunity.get("is_won", False),
            "close_date": opportunity.get("close_date"),
            "salesforce_join_method": join_method,
        })
    return {"leads": leads, "opportunities": opportunities, "funnel": funnel}


async def fetch_salesforce_funnel(
    lookback_days: int, limit: int | None = None
) -> List[Dict[str, Any]]:
    """Backward-compatible funnel-only interface."""
    return (await fetch_salesforce_data(lookback_days, limit))["funnel"]
