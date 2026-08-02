import asyncio
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.cloud import bigquery

from marketing_growth_agent.dto.models import CampaignMetrics, MarketingDataset
from .salesforce_mcp import fetch_salesforce_data


GCP_PROJECT_ID = os.getenv("MARKETING_GCP_PROJECT_ID", "atgeir-moae-dev")
DATASET_ID = os.getenv("MARKETING_BIGQUERY_DATASET", "marketing_agent")

TABLE_GOOGLE_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.google_ads"
TABLE_LINKEDIN_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.linkedin_ads"
TABLE_CAPTERRA_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.capterra"
TABLE_MICROSOFT_ADS = f"{GCP_PROJECT_ID}.{DATASET_ID}.microsoft_ads"


def _query(query: str, lookback_days: int) -> List[Dict[str, Any]]:
    client = bigquery.Client(project=GCP_PROJECT_ID)
    config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("days", "INT64", lookback_days)
    ])
    return [dict(row) for row in client.query(query, job_config=config).result()]


def _fetch_google_ads_sync(lookback_days: int) -> List[Dict[str, Any]]:
    return _query(f"""
        SELECT
            COALESCE(
                SAFE_CAST(report_date AS DATE),
                SAFE.PARSE_DATE('%Y-%m-%d', CAST(report_date AS STRING))
            ) AS report_date,
            campaign_id,
            campaign_name,
            clicks,
            impressions,
            spend,
            conversions AS platform_conversions
        FROM `{TABLE_GOOGLE_ADS}`
        WHERE COALESCE(
            SAFE_CAST(report_date AS DATE),
            SAFE.PARSE_DATE('%Y-%m-%d', CAST(report_date AS STRING))
        ) >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
    """, lookback_days)


def _fetch_linkedin_ads_sync(lookback_days: int) -> List[Dict[str, Any]]:
    return _query(f"""
        SELECT
            SAFE_CAST(date AS DATE) AS report_date,
            campaign_id,
            campaign_name,
            target_audience_segment,
            clicks,
            impressions,
            cost AS spend,
            total_conversions AS platform_conversions
        FROM `{TABLE_LINKEDIN_ADS}`
        WHERE SAFE_CAST(date AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
    """, lookback_days)


def _fetch_capterra_ads_sync(lookback_days: int) -> List[Dict[str, Any]]:
    return _query(f"""
        SELECT
            SAFE_CAST(date AS DATE) AS report_date,
            campaign_id,
            campaign_name,
            clicks,
            0 AS impressions,
            cost AS spend
            ,0 AS platform_conversions
        FROM `{TABLE_CAPTERRA_ADS}`
        WHERE SAFE_CAST(date AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
    """, lookback_days)


def _fetch_microsoft_ads_sync(lookback_days: int) -> List[Dict[str, Any]]:
    return _query(f"""
        SELECT
            SAFE_CAST(date AS DATE) AS report_date,
            campaign_id,
            campaign_name,
            clicks,
            impressions,
            spend,
            conversions AS platform_conversions
        FROM `{TABLE_MICROSOFT_ADS}`
        WHERE SAFE_CAST(date AS DATE) >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
    """, lookback_days)


async def fetch_google_ads(lookback_days: int) -> List[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_google_ads_sync, lookback_days)


async def fetch_linkedin_ads(lookback_days: int) -> List[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_linkedin_ads_sync, lookback_days)


async def fetch_capterra_ads(lookback_days: int) -> List[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_capterra_ads_sync, lookback_days)


async def fetch_microsoft_ads(lookback_days: int) -> List[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_microsoft_ads_sync, lookback_days)


def build_ad_platform_performance(
    google: List[Dict[str, Any]],
    linkedin: List[Dict[str, Any]],
    capterra: List[Dict[str, Any]],
    microsoft: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "google_ads": google,
        "linkedin_ads": linkedin,
        "capterra_ads": capterra,
        "microsoft_ads": microsoft,
        "totals": {
            "google_records": len(google),
            "linkedin_records": len(linkedin),
            "capterra_records": len(capterra),
            "microsoft_records": len(microsoft),
        },
    }


def build_crm_funnel_details(
    sf_funnel: List[Dict[str, Any]],
    leads: Optional[List[Dict[str, Any]]] = None,
    opportunities: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    leads = leads if leads is not None else sf_funnel
    opportunities = opportunities if opportunities is not None else [
        row for row in sf_funnel if row.get("opportunity_id")
    ]
    converted = [row for row in sf_funnel if row.get("opportunity_id")]
    won = [row for row in sf_funnel if row.get("is_won")]
    return {
        "funnel_records": sf_funnel,
        "leads": leads,
        "opportunities": opportunities,
        "summary": {
            "total_leads": len(leads),
            "total_opportunities": len(opportunities),
            "converted_leads_with_opportunity": len(converted),
            "won_opportunities": len(won),
        },
    }


def _year_month(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    return str(value or "")[:7]


def _channel_key(value: Any) -> str:
    source = _attribution_key(value)
    if any(token in source for token in ("google", "adwords", "paid search", "sem")):
        return "google_ads"
    if "linkedin" in source:
        return "linkedin_ads"
    if any(token in source for token in ("microsoft", "bing")):
        return "microsoft_ads"
    if "capterra" in source:
        return "capterra"
    return source


def build_marketing_payload(
    ad_performance: Dict[str, Any],
    sf_funnel: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create overall and monthly efficiency summaries for analysis agents."""
    sf_funnel = sf_funnel or []
    crm_overall: Dict[str, Dict[str, int]] = {}
    crm_monthly: Dict[tuple, Dict[str, int]] = {}
    crm_by_channel: Dict[str, Dict[str, int]] = {}
    crm_monthly_by_channel: Dict[tuple, Dict[str, int]] = {}
    for lead in sf_funnel:
        source = _attribution_key(
            lead.get("utm_campaign") or lead.get("lead_source") or "unknown"
        )
        has_opportunity = bool(lead.get("opportunity_id"))
        overall = crm_overall.setdefault(source, {"leads": 0, "opportunities": 0})
        overall["leads"] += 1
        overall["opportunities"] += int(has_opportunity)
        channel = _channel_key(lead.get("lead_source") or lead.get("utm_source"))
        channel_totals = crm_by_channel.setdefault(
            channel, {"leads": 0, "opportunities": 0}
        )
        channel_totals["leads"] += 1
        channel_totals["opportunities"] += int(has_opportunity)
        month = _year_month(lead.get("lead_created_date"))
        if month:
            monthly = crm_monthly.setdefault(
                (month, source), {"leads": 0, "opportunities": 0}
            )
            monthly["leads"] += 1
            monthly["opportunities"] += int(has_opportunity)
            monthly_channel = crm_monthly_by_channel.setdefault(
                (month, channel), {"leads": 0, "opportunities": 0}
            )
            monthly_channel["leads"] += 1
            monthly_channel["opportunities"] += int(has_opportunity)

    all_rows = []
    channel_rows = (
        ("Google Ads", ad_performance.get("google_ads", [])),
        ("LinkedIn Ads", ad_performance.get("linkedin_ads", [])),
        ("Microsoft Ads", ad_performance.get("microsoft_ads", [])),
        ("Capterra", ad_performance.get("capterra_ads", [])),
    )
    for channel, rows in channel_rows:
        all_rows.extend({**row, "channel": channel} for row in rows)

    channel_clicks = {}
    monthly_channel_clicks = {}
    for row in all_rows:
        platform = _channel_key(row["channel"])
        clicks = int(_number(row.get("clicks")))
        channel_clicks[platform] = channel_clicks.get(platform, 0) + clicks
        month_key = (_year_month(row.get("report_date")), platform)
        monthly_channel_clicks[month_key] = (
            monthly_channel_clicks.get(month_key, 0) + clicks
        )

    def aggregate(include_month: bool) -> Dict[tuple, Dict[str, Any]]:
        result: Dict[tuple, Dict[str, Any]] = {}
        for row in all_rows:
            month = _year_month(row.get("report_date"))
            campaign_id = str(row.get("campaign_id") or "")
            campaign_name = str(row.get("campaign_name") or campaign_id)
            key = (
                (month, row["channel"], campaign_id, campaign_name)
                if include_month
                else (row["channel"], campaign_id, campaign_name)
            )
            item = result.setdefault(
                key, {"spend": 0.0, "clicks": 0, "impressions": 0, "conversions": 0}
            )
            item["spend"] += _number(row.get("spend"))
            item["clicks"] += int(_number(row.get("clicks")))
            item["impressions"] += int(_number(row.get("impressions")))
            item["conversions"] += int(_number(row.get("platform_conversions")))
        return result

    overall_performance = []
    for (channel, campaign_id, campaign_name), metrics in aggregate(False).items():
        crm = crm_overall.get(_attribution_key(campaign_name), {})
        attribution_method = "campaign"
        if crm:
            leads = crm.get("leads", 0)
            opportunities = crm.get("opportunities", 0)
        else:
            attribution_method = "channel_click_share"
            platform = _channel_key(channel)
            channel_crm = crm_by_channel.get(
                platform, {"leads": 0, "opportunities": 0}
            )
            total_clicks = channel_clicks.get(platform, 0)
            weight = metrics["clicks"] / total_clicks if total_clicks else 0
            leads = round(channel_crm["leads"] * weight)
            opportunities = round(channel_crm["opportunities"] * weight)
        overall_performance.append({
            "channel": channel,
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "total_spend": round(metrics["spend"], 2),
            "total_clicks": metrics["clicks"],
            "total_impressions": metrics["impressions"],
            "platform_conversions": metrics["conversions"],
            "total_sf_leads": leads,
            "total_sf_opportunities": opportunities,
            "salesforce_attribution_method": attribution_method,
            "ctr_percent": _ratio(metrics["clicks"], metrics["impressions"], 100),
            "cpc": _ratio(metrics["spend"], metrics["clicks"]),
            "cpl": _ratio(metrics["spend"], leads) if leads else None,
            "lead_to_opp_conversion_rate": (
                _ratio(opportunities, leads, 100) if leads else None
            ),
            "cost_per_opportunity": (
                _ratio(metrics["spend"], opportunities) if opportunities else None
            ),
        })

    monthly_performance = []
    for (month, channel, campaign_id, campaign_name), metrics in aggregate(True).items():
        crm = crm_monthly.get((month, _attribution_key(campaign_name)), {})
        attribution_method = "campaign"
        if crm:
            leads = crm.get("leads", 0)
            opportunities = crm.get("opportunities", 0)
        else:
            attribution_method = "channel_click_share"
            platform = _channel_key(channel)
            channel_crm = crm_monthly_by_channel.get(
                (month, platform), {"leads": 0, "opportunities": 0}
            )
            total_clicks = monthly_channel_clicks.get((month, platform), 0)
            weight = metrics["clicks"] / total_clicks if total_clicks else 0
            leads = round(channel_crm["leads"] * weight)
            opportunities = round(channel_crm["opportunities"] * weight)
        monthly_performance.append({
            "year_month": month,
            "channel": channel,
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "spend": round(metrics["spend"], 2),
            "clicks": metrics["clicks"],
            "impressions": metrics["impressions"],
            "ad_conversions": metrics["conversions"],
            "sf_leads": leads,
            "sf_opportunities": opportunities,
            "salesforce_attribution_method": attribution_method,
            "monthly_ctr_percent": _ratio(
                metrics["clicks"], metrics["impressions"], 100
            ),
            "monthly_cpc": _ratio(metrics["spend"], metrics["clicks"]),
            "monthly_cpl": _ratio(metrics["spend"], leads) if leads else None,
            "monthly_lead_to_opp_rate": (
                _ratio(opportunities, leads, 100) if leads else None
            ),
        })

    return {
        "overall_performance": overall_performance,
        "monthly_performance": sorted(
            monthly_performance, key=lambda row: row["year_month"], reverse=True
        ),
        "salesforce_status": "available" if sf_funnel else "not_configured",
        "raw_leads_sample_count": len(sf_funnel),
        "raw_opps_sample_count": sum(
            bool(row.get("opportunity_id")) for row in sf_funnel
        ),
    }


def _ratio(numerator: float, denominator: float, multiplier: float = 1.0) -> float:
    return round((numerator / denominator) * multiplier, 2) if denominator else 0.0


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return 0.0


def calculate_metrics(campaign: CampaignMetrics) -> Dict[str, float]:
    return {
        "ctr": _ratio(campaign.clicks, campaign.impressions, 100),
        "cpc": _ratio(campaign.spend, campaign.clicks),
        "cpl": _ratio(campaign.spend, campaign.conversions),
        "cpo": _ratio(campaign.spend, campaign.opportunities),
        "qualified_lead_rate": _ratio(campaign.qualified_leads, campaign.conversions, 100),
        "opportunity_rate": _ratio(campaign.opportunities, campaign.qualified_leads, 100),
        "roas": _ratio(campaign.revenue, campaign.spend),
        "pipeline_roi": _ratio(campaign.pipeline_value, campaign.spend),
        "budget_utilization": _ratio(campaign.spend, campaign.budget, 100),
    }


def _attribution_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def build_marketing_dataset(
    ad_performance: Dict[str, Any],
    crm_funnel: Dict[str, Any],
    account_id: str,
    period: str,
    pipeline_target: float,
    default_target_cpl: float,
) -> Dict[str, Any]:
    """Build the normalized compatibility state used by downstream agents."""
    crm_by_campaign: Dict[str, List[Dict[str, Any]]] = {}
    for row in crm_funnel.get("funnel_records", []):
        key = _attribution_key(row.get("utm_campaign"))
        if key:
            crm_by_campaign.setdefault(key, []).append(row)
    crm_by_channel: Dict[str, List[Dict[str, Any]]] = {}
    for row in crm_funnel.get("funnel_records", []):
        channel = _channel_key(row.get("lead_source") or row.get("utm_source"))
        if channel:
            crm_by_channel.setdefault(channel, []).append(row)

    total_clicks_by_platform: Dict[str, int] = {}
    for platform, rows in (
        ("google_ads", ad_performance.get("google_ads", [])),
        ("linkedin_ads", ad_performance.get("linkedin_ads", [])),
        ("capterra", ad_performance.get("capterra_ads", [])),
        ("microsoft_ads", ad_performance.get("microsoft_ads", [])),
    ):
        total_clicks_by_platform[platform] = sum(
            int(_number(row.get("clicks"))) for row in rows
        )

    grouped: Dict[str, Dict[str, Any]] = {}
    channels = (
        ("google_ads", ad_performance.get("google_ads", [])),
        ("linkedin_ads", ad_performance.get("linkedin_ads", [])),
        ("capterra", ad_performance.get("capterra_ads", [])),
        ("microsoft_ads", ad_performance.get("microsoft_ads", [])),
    )
    for platform, rows in channels:
        for row in rows:
            campaign_id = str(row.get("campaign_id"))
            key = f"{platform}:{campaign_id}"
            item = grouped.setdefault(key, {
                "campaign_id": campaign_id,
                "platform": platform,
                "campaign_name": str(row.get("campaign_name") or campaign_id),
                "spend": 0.0,
                "budget": 0.0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0,
                "qualified_leads": 0,
                "opportunities": 0,
                "pipeline_value": 0.0,
                "revenue": 0.0,
                "target_cpl": default_target_cpl,
                "audience_segments": [],
            })
            item["spend"] += _number(row.get("spend"))
            item["impressions"] += int(_number(row.get("impressions")))
            item["clicks"] += int(_number(row.get("clicks")))
            item["conversions"] += int(_number(row.get("platform_conversions")))
            segment = row.get("target_audience_segment")
            if segment and segment not in item["audience_segments"]:
                item["audience_segments"].append({"name": str(segment)})

    campaigns = []
    for item in grouped.values():
        matches = crm_by_campaign.get(_attribution_key(item["campaign_name"]), [])
        if not matches:
            matches = crm_by_campaign.get(_attribution_key(item["campaign_id"]), [])
        qualified_statuses = {"qualified", "converted", "mql", "sql", "sales qualified"}
        if matches:
            qualified = sum(
                str(row.get("lead_status") or "").strip().casefold()
                in qualified_statuses
                for row in matches
            )
            opportunities = [row for row in matches if row.get("opportunity_id")]
            pipeline_value = sum(
                _number(row.get("deal_size")) for row in opportunities
            )
            revenue = sum(
                _number(row.get("deal_size"))
                for row in opportunities if row.get("is_won")
            )
        else:
            channel_rows = crm_by_channel.get(item["platform"], [])
            total_clicks = total_clicks_by_platform.get(item["platform"], 0)
            weight = item["clicks"] / total_clicks if total_clicks else 0
            qualified = round(sum(
                str(row.get("lead_status") or "").strip().casefold()
                in qualified_statuses
                for row in channel_rows
            ) * weight)
            channel_opportunities = [
                row for row in channel_rows if row.get("opportunity_id")
            ]
            opportunities = [None] * round(len(channel_opportunities) * weight)
            pipeline_value = sum(
                _number(row.get("deal_size")) for row in channel_opportunities
            ) * weight
            revenue = sum(
                _number(row.get("deal_size"))
                for row in channel_opportunities if row.get("is_won")
            ) * weight
        item["qualified_leads"] = qualified
        item["opportunities"] = len(opportunities)
        item["pipeline_value"] = pipeline_value
        item["revenue"] = revenue
        campaign = CampaignMetrics.model_validate(item)
        campaign.derived_metrics = calculate_metrics(campaign)
        campaigns.append(campaign.model_dump())

    return {
        "account_id": account_id,
        "period": period,
        "pipeline_target": pipeline_target,
        "campaigns": campaigns,
    }


def load_marketing_dataset(path: Union[str, Path]) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        dataset = MarketingDataset.model_validate(json.load(handle))
    campaigns = []
    for campaign in dataset.campaigns:
        campaign.derived_metrics = calculate_metrics(campaign)
        campaigns.append(campaign.model_dump())
    return {
        "account_id": dataset.account_id,
        "period": dataset.period,
        "pipeline_target": dataset.pipeline_target,
        "campaigns": campaigns,
    }


class MarketingDataCollectionAgent(BaseAgent):
    """Collect ad and CRM data and publish raw-domain plus normalized state."""

    async def _run_async_impl(self, ctx):
        fixture_path = ctx.session.state.get("marketing_data_path")
        if fixture_path:
            loop = asyncio.get_event_loop()
            marketing_dataset = await loop.run_in_executor(
                None, load_marketing_dataset, fixture_path
            )
            ctx.session.state["marketing_dataset"] = marketing_dataset
            yield Event(
                author=self.name,
                content=None,
                actions=EventActions(
                    state_delta={"marketing_dataset": marketing_dataset}
                ),
            )
            return

        lookback_days = int(ctx.session.state.get(
            "lookback_days", os.getenv("MARKETING_LOOKBACK_DAYS", "365")
        ))
        if lookback_days < 1 or lookback_days > 730:
            raise ValueError("lookback_days must be between 1 and 730")

        salesforce_enabled = str(
            ctx.session.state.get(
                "salesforce_enabled",
                os.getenv("MARKETING_SALESFORCE_ENABLED", "true"),
            )
        ).strip().casefold() in {"1", "true", "yes", "on"}

        async def fetch_salesforce_or_empty() -> Dict[str, List[Dict[str, Any]]]:
            if not salesforce_enabled:
                return {"leads": [], "opportunities": [], "funnel": []}
            return await fetch_salesforce_data(lookback_days)

        results = await asyncio.gather(
            fetch_salesforce_or_empty(),
            fetch_google_ads(lookback_days),
            fetch_linkedin_ads(lookback_days),
            fetch_capterra_ads(lookback_days),
            fetch_microsoft_ads(lookback_days),
            return_exceptions=True,
        )
        source_names = ("salesforce", "google_ads", "linkedin_ads", "capterra", "microsoft_ads")
        source_errors = {
            name: str(result)
            for name, result in zip(source_names, results)
            if isinstance(result, Exception)
        }
        sf_data, google, linkedin, capterra, microsoft = [
            [] if isinstance(result, Exception) else result for result in results
        ]
        if not isinstance(sf_data, dict):
            sf_data = {"leads": [], "opportunities": [], "funnel": []}
        sf_funnel = sf_data.get("funnel", [])
        ad_performance = build_ad_platform_performance(
            google, linkedin, capterra, microsoft
        )
        crm_funnel = build_crm_funnel_details(
            sf_funnel,
            leads=sf_data.get("leads", []),
            opportunities=sf_data.get("opportunities", []),
        )
        marketing_payload = build_marketing_payload(ad_performance, sf_funnel)
        if salesforce_enabled and not source_errors.get("salesforce"):
            marketing_payload["salesforce_status"] = "available"
        elif source_errors.get("salesforce"):
            marketing_payload["salesforce_status"] = "error"
        marketing_payload["source_errors"] = source_errors
        ctx.session.state["ad_platform_performance"] = ad_performance
        ctx.session.state["crm_funnel_details"] = crm_funnel
        ctx.session.state["marketing_payload"] = marketing_payload

        configured_target = ctx.session.state.get(
            "pipeline_target", os.getenv("MARKETING_PIPELINE_TARGET", "1500000")
        )
        ctx.session.state["marketing_dataset"] = build_marketing_dataset(
            ad_performance=ad_performance,
            crm_funnel=crm_funnel,
            account_id=ctx.session.state.get("marketing_account_id", "all-accounts"),
            period=ctx.session.state.get("reporting_period", date.today().strftime("%Y-%m")),
            pipeline_target=float(configured_target),
            default_target_cpl=float(ctx.session.state.get(
                "default_target_cpl", os.getenv("MARKETING_DEFAULT_TARGET_CPL", "150")
            )),
        )
        yield Event(
            author=self.name,
            content=None,
            actions=EventActions(state_delta={
                "ad_platform_performance": ad_performance,
                "crm_funnel_details": crm_funnel,
                "marketing_payload": marketing_payload,
                "marketing_dataset": ctx.session.state["marketing_dataset"],
            }),
        )


# Backward-compatible name used by SequentialAgent.py.
DataCollectionAgent = MarketingDataCollectionAgent
