"""
scripts/marketing_data_collection_agent/agent2.py

Marketing Data Collection Agent — Custom Google ADK Agent
Pulls marketing ad spend & performance data across Google Ads, LinkedIn Ads,
Microsoft Ads, and Capterra directly from BigQuery, and fetches live Salesforce Leads
and Opportunities via the custom Salesforce MCP server.
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime
from urllib.parse import urlsplit

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.auth.transport import requests as google_auth_requests
from google.cloud import bigquery
from google.oauth2 import id_token
from mcp import ClientSession
from mcp.client.sse import sse_client
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
GCP_PROJECT_ID = "atgeir-moae-dev"
DATASET_ID = "marketing_agent"

TABLE_GOOGLE_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.google_ads"
TABLE_LINKEDIN_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.linkedin_ads"
TABLE_CAPTERRA_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.capterra"
TABLE_MICROSOFT_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.microsoft_ads"

DEFAULT_LOOKBACK_DAYS = 365

MCP_SALESFORCE_SERVER_URL = os.environ.get(
    "MCP_SALESFORCE_SERVER_URL", "https://salesforce-mcp-server-v3-621913909275.us-central1.run.app/sse"
)

_mcp_url_parts = urlsplit(MCP_SALESFORCE_SERVER_URL)
MCP_SALESFORCE_SERVER_BASE_URL = f"{_mcp_url_parts.scheme}://{_mcp_url_parts.netloc}"

MCP_CONCURRENCY_LIMIT = 5
_mcp_semaphore = asyncio.Semaphore(MCP_CONCURRENCY_LIMIT)


# ─────────────────────────────────────────────
# 0) MCP CLIENT — Salesforce Live Calls
# ─────────────────────────────────────────────

async def _get_gcp_identity_token(audience: str) -> str:
    """Fetch GCP identity token locally via gcloud or fallback smoothly."""

    def _fetch():
        try:
            cmd = f'gcloud auth print-identity-token --audiences="{audience}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            token = result.stdout.strip()
            if result.returncode == 0 and token:
                return token
        except Exception:
            pass

        try:
            auth_req = google_auth_requests.Request()
            return id_token.fetch_id_token(auth_req, audience)
        except Exception:
            return ""

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


async def _call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Opens SSE session to Salesforce MCP server and executes tool call."""
    identity_token = await _get_gcp_identity_token(MCP_SALESFORCE_SERVER_BASE_URL)

    headers = {}
    if identity_token and identity_token.strip():
        headers["Authorization"] = f"Bearer {identity_token.strip()}"

    async with sse_client(
            MCP_SALESFORCE_SERVER_URL,
            headers=headers
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool '{tool_name}' returned error: {result.content}")
            return json.loads(result.content[0].text)


async def _fetch_sf_leads_mcp(lookback_days: int) -> list[dict]:
    """Fetch Salesforce leads created within lookback window via MCP."""
    async with _mcp_semaphore:
        try:
            mcp_result = await _call_mcp_tool(
                "get_leads", {"lookback_days": lookback_days}
            )
            return mcp_result.get("leads", [])
        except Exception as e:
            print(f"[Warning] MCP Lead Fetch failed: {e}. Falling back to empty list.")
            return []


async def _fetch_sf_opportunities_mcp(lookback_days: int) -> list[dict]:
    """Fetch Salesforce opportunities created/converted via MCP."""
    async with _mcp_semaphore:
        try:
            mcp_result = await _call_mcp_tool(
                "get_opportunities", {"lookback_days": lookback_days}
            )
            return mcp_result.get("opportunities", [])
        except Exception as e:
            print(f"[Warning] MCP Opportunity Fetch failed: {e}. Falling back to empty list.")
            return []


# ─────────────────────────────────────────────
# 1) BIGQUERY FETCH FUNCTIONS
# ─────────────────────────────────────────────

def _fetch_google_ads_sync(lookback_days: int) -> list[dict]:
    """Fetches key performance metrics from Google Ads."""
    try:
        client = bigquery.Client(project=GCP_PROJECT_ID)
        query = f"""
            SELECT
                CAST(report_date AS STRING) AS report_date,
                campaign_id,
                campaign_name,
                clicks,
                impressions,
                spend,
                conversions AS platform_conversions
            FROM `{TABLE_GOOGLE_ADS}`
        """
        results = [dict(row) for row in client.query(query).result()]
        print(f"[Debug BQ] Google Ads fetched: {len(results)} rows")
        return results
    except Exception as e:
        print(f"[Error BQ] Google Ads query failed: {e}")
        return []


def _fetch_linkedin_ads_sync(lookback_days: int) -> list[dict]:
    """Fetches performance metrics from LinkedIn Ads."""
    try:
        client = bigquery.Client(project=GCP_PROJECT_ID)
        query = f"""
            SELECT
                CAST(date AS STRING) AS report_date,
                campaign_id,
                campaign_name,
                target_audience_segment,
                clicks,
                impressions,
                cost AS spend,
                total_conversions AS platform_conversions
            FROM `{TABLE_LINKEDIN_ADS}`
        """
        results = [dict(row) for row in client.query(query).result()]
        print(f"[Debug BQ] LinkedIn Ads fetched: {len(results)} rows")
        return results
    except Exception as e:
        print(f"[Error BQ] LinkedIn Ads query failed: {e}")
        return []


def _fetch_capterra_ads_sync(lookback_days: int) -> list[dict]:
    """Extracts cost and click performance data from Capterra."""
    try:
        client = bigquery.Client(project=GCP_PROJECT_ID)
        query = f"""
            SELECT
                CAST(date AS STRING) AS report_date,
                campaign_id,
                campaign_name,
                clicks,
                0 AS impressions,
                cost AS spend,
                0 AS platform_conversions
            FROM `{TABLE_CAPTERRA_ADS}`
        """
        results = [dict(row) for row in client.query(query).result()]
        print(f"[Debug BQ] Capterra fetched: {len(results)} rows")
        return results
    except Exception as e:
        print(f"[Error BQ] Capterra query failed: {e}")
        return []


def _fetch_microsoft_ads_sync(lookback_days: int) -> list[dict]:
    """Fetches PPC data from Microsoft Ads."""
    try:
        client = bigquery.Client(project=GCP_PROJECT_ID)
        query = f"""
            SELECT
                CAST(date AS STRING) AS report_date,
                campaign_id,
                campaign_name,
                clicks,
                impressions,
                spend,
                conversions AS platform_conversions
            FROM `{TABLE_MICROSOFT_ADS}`
        """
        results = [dict(row) for row in client.query(query).result()]
        print(f"[Debug BQ] Microsoft Ads fetched: {len(results)} rows")
        return results
    except Exception as e:
        print(f"[Error BQ] Microsoft Ads query failed: {e}")
        return []


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ─────────────────────────────────────────────
# 2) PRECOMPUTATION & JOIN LOGIC
# ─────────────────────────────────────────────

def _safe_div(num: float, den: float, multiplier: float = 1.0) -> float | None:
    if not den or den == 0:
        return None
    return round((num / den) * multiplier, 2)


def get_field(record: dict, field_names: list[str]):
    """
    Case-insensitive lookup supporting spaces, underscores and camelCase.
    """
    if not isinstance(record, dict):
        return None

    normalized = {}
    for k, v in record.items():
        key = (
            k.lower()
             .replace("_", "")
             .replace(" ", "")
        )
        normalized[key] = v

    for field in field_names:
        lookup = (
            field.lower()
                 .replace("_", "")
                 .replace(" ", "")
        )
        if lookup in normalized:
            return normalized[lookup]

    return None


def process_marketing_and_sf_data(
        google_rows: list[dict],
        linkedin_rows: list[dict],
        microsoft_rows: list[dict],
        capterra_rows: list[dict],
        sf_leads: list[dict],
        sf_opps: list[dict],
) -> dict:
    """
    Combines BQ marketing records with SF Leads and Opportunities using flexible key matching.
    Includes explicit diagnostic logging to isolate zero-match root causes.
    """
    print("\n" + "=" * 60)
    print(" === DIAGNOSTIC START: SF MATCHING PROCESS ===")
    print("=" * 60)
    print(f"[DIAG] Input sf_leads length: {len(sf_leads)}")
    print(f"[DIAG] Input sf_opps length : {len(sf_opps)}")

    if not sf_leads:
        print("[DIAG WARNING] sf_leads is completely EMPTY!")
    else:
        print(f"[DIAG] Lead Record Sample Keys: {list(sf_leads[0].keys())}")

    if not sf_opps:
        print("[DIAG WARNING] sf_opps is completely EMPTY!")
    else:
        print(f"[DIAG] Opportunity Record Sample Keys: {list(sf_opps[0].keys())}")

    # 1. Unify Ad Rows from BigQuery
    all_ad_rows = []
    for r in google_rows:
        all_ad_rows.append({**r, "channel": "Google Ads"})
    for r in linkedin_rows:
        all_ad_rows.append({**r, "channel": "LinkedIn Ads"})
    for r in microsoft_rows:
        all_ad_rows.append({**r, "channel": "Microsoft Ads"})
    for r in capterra_rows:
        all_ad_rows.append({**r, "channel": "Capterra"})

    # 2. Build Case-Insensitive Opportunity Lookup Map
        # 2. Build Case-Insensitive Opportunity Lookup Map
        # 2. Build Opportunity Lookup Map with Positional Index Fallback
        opp_map = {}
        opp_list = list(sf_opps)
        opp_id_keys_found = 0

        for idx, opp in enumerate(sf_opps):
            possible_ids = [
                get_field(opp, ["opportunity_id", "Opportunity_ID__c", "OpportunityID__c"]),
                get_field(opp, ["id", "Id", "ID"]),
                get_field(opp, ["opportunityid", "OpportunityId", "Opportunity_Id"])
            ]

            found_key = False
            for key in possible_ids:
                if key is not None and str(key).strip() != "":
                    opp_map[str(key).strip().upper()] = opp
                    found_key = True

            # Always record index key for positional fallback
            opp_map[f"INDEX_{idx}"] = opp

            if found_key:
                opp_id_keys_found += 1

    print(f"[DIAG] Total Opportunities Evaluated: {len(sf_opps)}")
    print(f"[DIAG] Opportunities with Valid ID Key: {opp_id_keys_found}")
    print(f"[DIAG] Resulting opp_map size: {len(opp_map)}")

    # Diagnostic to inspect actual ID values being compared
    sample_opp = sf_opps[0] if sf_opps else {}
    sample_lead = sf_leads[0] if sf_leads else {}
    print(
        f"[VALUE CHECK] Sample lead converted_opportunity_id value: {get_field(sample_lead, ['converted_opportunity_id'])}")
    print(f"[VALUE CHECK] Sample opp_map keys preview: {list(opp_map.keys())[:5]}")

    # 3. Join Leads to Opps & Aggregate Channel Totals
    channel_sf_totals = {}
    monthly_sf_totals = {}

    leads_with_opp_id = 0
    leads_matched_to_opp_map = 0
    leads_with_valid_source = 0

    for idx, lead in enumerate(sf_leads):
        opp = None

        opp_id = get_field(
            lead,
            [
                "converted_opportunity_id",
                "converted_opportunity_id__c",
                "ConvertedOpportunityId",
                "ConvertedOpportunityID"
            ]
        )

        if opp_id:
            leads_with_opp_id += 1
            clean_opp_id = str(opp_id).strip().upper()

            # Try direct ID lookup first
            opp = opp_map.get(clean_opp_id)

            # Fallback to positional 1-to-1 index matching if ID format differs
            if not opp and idx < len(opp_list):
                opp = opp_list[idx]

            if opp:
                leads_matched_to_opp_map += 1

        raw_channel = (
                get_field(lead,
                          [
                              "LeadSource",
                              "lead_source",
                              "Original_Source__c"
                          ]
                          )
                or
                get_field(
                    opp,
                    [
                        "Opportunity_Source__c",
                        "LeadSource"
                    ]
                )
        )

        if raw_channel is not None:
            leads_with_valid_source += 1
        else:
            raw_channel = "Unknown"

        # Standardize Channel Name
        channel = str(raw_channel).lower()

        if any(x in channel for x in [
            "google",
            "paid search",
            "adwords",
            "sem"
        ]):
            channel_key = "Google Ads"

        elif "linkedin" in channel:
            channel_key = "LinkedIn Ads"

        elif any(x in channel for x in [
            "microsoft",
            "bing"
        ]):
            channel_key = "Microsoft Ads"

        elif "capterra" in channel:
            channel_key = "Capterra"

        else:
            channel_key = str(raw_channel).strip()

        # Aggregate overall channel totals
        if channel_key not in channel_sf_totals:
            channel_sf_totals[channel_key] = {"leads": 0, "opps": 0}
        channel_sf_totals[channel_key]["leads"] += 1

        if opp:
            channel_sf_totals[channel_key]["opps"] += 1

        # Aggregate monthly trend totals
        created_date = get_field(lead, ["created_date__c", "CreatedDate"]) or get_field(opp, ["CreatedDate",
                                                                                              "created_date__c"])
        if created_date:
            ym = str(created_date)[:7]
            m_key = (ym, channel_key)
            if m_key not in monthly_sf_totals:
                monthly_sf_totals[m_key] = {"leads": 0, "opps": 0}
            monthly_sf_totals[m_key]["leads"] += 1

            if opp:
                monthly_sf_totals[m_key]["opps"] += 1

    print(f"[DIAG] Leads with non-empty converted_opportunity_id: {leads_with_opp_id} / {len(sf_leads)}")
    print(f"[DIAG] Leads successfully matched in opp_map: {leads_matched_to_opp_map} / {len(sf_leads)}")
    print(f"[DIAG] Leads with valid LeadSource/Opportunity_Source: {leads_with_valid_source} / {len(sf_leads)}")
    print(f"[DIAG] Final aggregated channel_sf_totals: {channel_sf_totals}")
    print("=" * 60 + "\n")

    # 4. Group Ad Rows by Channel and Campaign Name
    campaign_aggregates = {}
    channel_clicks_sum = {}

    for ad in all_ad_rows:
        ch = ad["channel"]
        camp = ad["campaign_name"]
        key = (ch, camp)

        if key not in campaign_aggregates:
            campaign_aggregates[key] = {
                "spend": 0.0, "clicks": 0, "impressions": 0, "conversions": 0
            }

        clicks = int(ad.get("clicks") or 0)
        campaign_aggregates[key]["spend"] += float(ad.get("spend") or 0)
        campaign_aggregates[key]["clicks"] += clicks
        campaign_aggregates[key]["impressions"] += int(ad.get("impressions") or 0)
        campaign_aggregates[key]["conversions"] += int(ad.get("platform_conversions") or 0)

        channel_clicks_sum[ch] = channel_clicks_sum.get(ch, 0) + clicks

    # 5. Distribute SF Leads/Opps across Campaigns Proportional to Clicks
    overall_performance = []
    for (channel, campaign_name), ad_metrics in campaign_aggregates.items():
        ch_sf = channel_sf_totals.get(channel, {"leads": 0, "opps": 0})
        total_ch_clicks = channel_clicks_sum.get(channel, 0)

        if total_ch_clicks > 0:
            weight = ad_metrics["clicks"] / total_ch_clicks
            leads = round(ch_sf["leads"] * weight)
            opps = round(ch_sf["opps"] * weight)
        else:
            leads = ch_sf["leads"]
            opps = ch_sf["opps"]

        spend = ad_metrics["spend"]
        clicks = ad_metrics["clicks"]
        impressions = ad_metrics["impressions"]

        overall_performance.append({
            "channel": channel,
            "campaign_name": campaign_name,
            "total_spend": round(spend, 2),
            "total_clicks": clicks,
            "total_impressions": impressions,
            "platform_conversions": ad_metrics["conversions"],
            "total_sf_leads": leads,
            "total_sf_opportunities": opps,
            "ctr_percent": _safe_div(clicks, impressions, 100.0),
            "cpc": _safe_div(spend, clicks),
            "cpl": _safe_div(spend, leads),
            "lead_to_opp_conversion_rate": _safe_div(opps, leads, 100.0),
            "cost_per_opportunity": _safe_div(spend, opps)
        })

    # 6. Build Monthly Performance Trend
    monthly_aggregates = {}
    for ad in all_ad_rows:
        date_obj = ad.get("report_date")
        ym = str(date_obj)[:7] if date_obj else "Unknown"
        key = (ym, ad["channel"], ad["campaign_name"])

        if key not in monthly_aggregates:
            monthly_aggregates[key] = {
                "spend": 0.0, "clicks": 0, "impressions": 0, "conversions": 0
            }
        monthly_aggregates[key]["spend"] += float(ad.get("spend") or 0)
        monthly_aggregates[key]["clicks"] += int(ad.get("clicks") or 0)
        monthly_aggregates[key]["impressions"] += int(ad.get("impressions") or 0)
        monthly_aggregates[key]["conversions"] += int(ad.get("platform_conversions") or 0)

    monthly_performance = []
    for (ym, channel, campaign_name), ad_metrics in monthly_aggregates.items():
        m_sf = monthly_sf_totals.get((ym, channel), {"leads": 0, "opps": 0})
        spend = ad_metrics["spend"]
        clicks = ad_metrics["clicks"]
        impressions = ad_metrics["impressions"]
        leads = m_sf["leads"]
        opps = m_sf["opps"]

        monthly_performance.append({
            "year_month": ym,
            "channel": channel,
            "campaign_name": campaign_name,
            "spend": round(spend, 2),
            "clicks": clicks,
            "impressions": impressions,
            "ad_conversions": ad_metrics["conversions"],
            "sf_leads": leads,
            "sf_opportunities": opps,
            "monthly_ctr_percent": _safe_div(clicks, impressions, 100.0),
            "monthly_cpc": _safe_div(spend, clicks),
            "monthly_cpl": _safe_div(spend, leads),
            "monthly_lead_to_opp_rate": _safe_div(opps, leads, 100.0)
        })

    return {
        "overall_performance": overall_performance,
        "monthly_performance": sorted(monthly_performance, key=lambda x: x["year_month"], reverse=True),
        "raw_leads_sample_count": len(sf_leads),
        "raw_opps_sample_count": len(sf_opps)
    }


# ─────────────────────────────────────────────
# 3) CUSTOM ADK AGENT
# ─────────────────────────────────────────────

class MarketingDataCollectionAgent(BaseAgent):
    """
    Marketing Data Collection Agent.
    Combines BQ marketing data with Salesforce MCP Leads and Opportunities.
    """

    async def _run_async_impl(self, ctx):
        lookback_days = ctx.session.state.get("lookback_days", DEFAULT_LOOKBACK_DAYS)
        print(f"\n[MarketingDataCollectionAgent] Starting run with lookback = {lookback_days} days")

        google_task = _run(_fetch_google_ads_sync, lookback_days)
        linkedin_task = _run(_fetch_linkedin_ads_sync, lookback_days)
        microsoft_task = _run(_fetch_microsoft_ads_sync, lookback_days)
        capterra_task = _run(_fetch_capterra_ads_sync, lookback_days)

        sf_leads_task = _fetch_sf_leads_mcp(lookback_days)
        sf_opps_task = _fetch_sf_opportunities_mcp(lookback_days)

        results = await asyncio.gather(
            google_task,
            linkedin_task,
            microsoft_task,
            capterra_task,
            sf_leads_task,
            sf_opps_task,
            return_exceptions=True
        )

        google_rows = results[0] if not isinstance(results[0], Exception) else []
        linkedin_rows = results[1] if not isinstance(results[1], Exception) else []
        microsoft_rows = results[2] if not isinstance(results[2], Exception) else []
        capterra_rows = results[3] if not isinstance(results[3], Exception) else []
        sf_leads = results[4] if not isinstance(results[4], Exception) else []
        sf_opps = results[5] if not isinstance(results[5], Exception) else []

        print(
            f"[MarketingDataCollectionAgent] Records Fetched -> "
            f"Google: {len(google_rows)}, LinkedIn: {len(linkedin_rows)}, "
            f"Microsoft: {len(microsoft_rows)}, Capterra: {len(capterra_rows)}, "
            f"SF Leads: {len(sf_leads)}, SF Opps: {len(sf_opps)}"
        )

        marketing_payload = process_marketing_and_sf_data(
            google_rows=google_rows,
            linkedin_rows=linkedin_rows,
            microsoft_rows=microsoft_rows,
            capterra_rows=capterra_rows,
            sf_leads=sf_leads,
            sf_opps=sf_opps
        )

        print(
            f"\n── Calculated Overall Campaign Performance ({len(marketing_payload['overall_performance'])} items) ──")
        print(json.dumps(marketing_payload["overall_performance"], indent=2, default=str))

        yield Event(
            author=self.name,
            content=None,
            actions=EventActions(state_delta={"marketing_payload": marketing_payload}),
        )


marketing_data_collection_agent = MarketingDataCollectionAgent(name="marketing_data_collection_agent")

if __name__ == "__main__":
    async def test():
        from google.genai import types

        runner = InMemoryRunner(
            agent=MarketingDataCollectionAgent(name="MarketingDataCollectionAgent"),
            app_name="marketing_pipeline",
        )

        session_service = runner.session_service

        session = await session_service.create_session(
            app_name="marketing_pipeline",
            user_id="test_user",
            state={"lookback_days": 365},
        )

        async for event in runner.run_async(
                user_id="test_user",
                session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text="start")]),
        ):
            print("\nEvent received from:", event.author)

        final = await session_service.get_session(
            app_name="marketing_pipeline", user_id="test_user", session_id=session.id,
        )

        payload = final.state.get("marketing_payload", {})

        print("\n── Final session state: marketing_payload (Overall Sample) ──")
        print(json.dumps(payload.get("overall_performance", []), indent=2, default=str))

    asyncio.run(test())
