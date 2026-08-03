"""MCP server exposing read-only Salesforce Lead and Opportunity tools."""

import os

from mcp.server.fastmcp import FastMCP

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .salesforce_client import (
    fetch_opportunities_for_lead,
    fetch_record_by_id,
    fetch_records,
)


mcp = FastMCP(
    "salesforce-lead-opportunity-server",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
    stateless_http=True,
    json_response=True,
    instructions=(
        "Read-only access to the Salesforce Lead and Opportunity objects. "
        "The server does not accept arbitrary SOQL and exposes no create, "
        "update, or delete operation."
    ),
)


@mcp.tool()
async def get_leads(
    limit: int = 100,
    modified_since: str | None = None,
) -> dict:
    """Fetch Salesforce Leads, newest first.

    Args:
        limit: Maximum records to return.
        modified_since: Optional UTC timestamp such as
            2026-07-01T00:00:00Z.
    """
    return await fetch_records(
        "Lead",
        limit=limit,
        order_by="CreatedDate",
        order_direction="DESC",
        modified_since=modified_since,
    )


@mcp.tool()
async def get_opportunities(
    limit: int = 100,
    modified_since: str | None = None,
) -> dict:
    """Fetch Salesforce Opportunities, newest first."""
    return await fetch_records(
        "Opportunity",
        limit=limit,
        order_by="CreatedDate",
        order_direction="DESC",
        modified_since=modified_since,
    )


@mcp.tool()
async def get_lead_by_id(lead_id: str) -> dict:
    """Fetch one Lead by its 15- or 18-character Salesforce Id."""
    return await fetch_record_by_id("Lead", lead_id)


@mcp.tool()
async def get_opportunity_by_id(opportunity_id: str) -> dict:
    """Fetch one Opportunity by its 15- or 18-character Salesforce Id."""
    return await fetch_record_by_id("Opportunity", opportunity_id)


@mcp.tool()
async def get_converted_opportunity_for_lead(lead_id: str) -> dict:
    """Fetch a Lead and, when converted, its standard converted Opportunity."""
    lead_result = await fetch_record_by_id("Lead", lead_id)
    lead = lead_result["record"]

    if not lead:
        return {"lead": None, "opportunity": None}

    converted_opportunity_id = lead.get("converted_opportunity_id")
    if not converted_opportunity_id:
        return {"lead": lead, "opportunity": None}

    opportunity_result = await fetch_opportunities_for_lead(
        converted_opportunity_id
    )
    return {
        "lead": lead,
        "opportunity": opportunity_result["opportunity"],
    }


if __name__ == "__main__":
    # Recommended production transport for current MCP Python SDK.
    mcp.run(transport="streamable-http")
