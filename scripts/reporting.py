"""Combine pipeline state into one campaign-oriented report."""

from typing import Any, Dict, List


def _dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value if isinstance(value, dict) else {}


def build_campaign_wise_report(state: Dict[str, Any]) -> Dict[str, Any]:
    dataset = _dict(state.get("marketing_dataset"))
    analyses = _dict(state.get("campaign_analysis_results"))
    growth = _dict(state.get("growth_assessment_result"))
    actions = _dict(state.get("actions_taken"))
    payload = _dict(state.get("marketing_payload"))

    analysis_by_id = {
        str(item.get("campaign_id")): item
        for item in analyses.get("campaigns", [])
    }
    growth_by_id = {
        str(item.get("campaign_id")): item
        for item in growth.get("campaign_assessments", [])
    }
    budgets_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for item in growth.get("budget_recommendations", []):
        budgets_by_id.setdefault(str(item.get("campaign_id")), []).append(item)

    categories_by_id: Dict[str, str] = {}
    for group in growth.get("performance_groups", []):
        for campaign_id in group.get("campaign_ids", []):
            categories_by_id[str(campaign_id)] = group.get("category")

    monthly_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for item in payload.get("monthly_performance", []):
        monthly_by_id.setdefault(str(item.get("campaign_id")), []).append(item)

    overall_by_id = {
        str(item.get("campaign_id")): item
        for item in payload.get("overall_performance", [])
    }

    actions_by_id: Dict[str, List[Dict[str, Any]]] = {}
    portfolio_actions = []
    for item in actions.get("actions", []):
        campaign_ids = []
        if item.get("campaign_id"):
            campaign_ids.append(str(item["campaign_id"]))
        campaign_ids.extend(
            str(value) for value in item.get("payload", {}).get("campaign_ids", [])
        )
        if campaign_ids:
            for campaign_id in set(campaign_ids):
                actions_by_id.setdefault(campaign_id, []).append(item)
        else:
            portfolio_actions.append(item)

    campaigns = []
    for campaign in dataset.get("campaigns", []):
        campaign_id = str(campaign.get("campaign_id"))
        campaigns.append({
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("campaign_name"),
            "channel": campaign.get("platform"),
            "performance_category": categories_by_id.get(campaign_id),
            "metrics": {
                "spend": campaign.get("spend"),
                "impressions": campaign.get("impressions"),
                "clicks": campaign.get("clicks"),
                "platform_conversions": campaign.get("conversions"),
                "qualified_leads": campaign.get("qualified_leads"),
                "opportunities": campaign.get("opportunities"),
                "pipeline_value": campaign.get("pipeline_value"),
                "revenue": campaign.get("revenue"),
                **campaign.get("derived_metrics", {}),
            },
            "crm_efficiency": overall_by_id.get(campaign_id, {}),
            "monthly_performance": monthly_by_id.get(campaign_id, []),
            "analysis": analysis_by_id.get(campaign_id, {}),
            "growth_assessment": growth_by_id.get(campaign_id, {}),
            "budget_recommendations": budgets_by_id.get(campaign_id, []),
            "proposed_actions": actions_by_id.get(campaign_id, []),
        })

    return {
        "reporting_period": dataset.get("period"),
        "pipeline_target": dataset.get("pipeline_target"),
        "campaign_count": len(campaigns),
        "campaign_wise_results": campaigns,
        "portfolio_summary": {
            key: growth.get(key)
            for key in (
                "forecast_period",
                "forecasted_qualified_leads",
                "forecasted_opportunities",
                "forecasted_pipeline",
                "target_attainment",
                "overall_growth_risk",
                "channel_efficiency",
                "channel_forecasts",
                "channel_budget_allocation",
                "high_intent_buyer_profiles",
                "ideal_customer_profile_summary",
                "target_account_criteria",
                "data_gaps",
                "recommended_next_steps",
                "executive_summary",
            )
        },
        "portfolio_actions": portfolio_actions,
        "source_errors": payload.get("source_errors", {}),
    }
