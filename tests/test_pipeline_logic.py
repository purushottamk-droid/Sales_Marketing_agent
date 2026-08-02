import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from marketing_growth_agent.dto.models import CampaignMetrics
from marketing_growth_agent.scripts.data_collection_agent.agent import (
    build_marketing_payload,
    calculate_metrics,
    load_marketing_dataset,
)
from marketing_growth_agent.scripts.decision_action_agent.agent import evaluate_actions
from marketing_growth_agent.scripts.reporting import build_campaign_wise_report
from marketing_growth_agent.scripts.data_collection_agent.salesforce_mcp import (
    fetch_salesforce_data,
    fetch_salesforce_funnel,
)


FIXTURE = Path(__file__).parent / "fixtures" / "marketing_data.json"


class MetricTests(unittest.TestCase):
    def test_calculates_kpis_without_llm_arithmetic(self):
        campaign = CampaignMetrics(
            campaign_id="one", platform="google_ads", campaign_name="Test",
            spend=1000, budget=2000, impressions=10000, clicks=500,
            conversions=20, qualified_leads=10, opportunities=2,
            pipeline_value=10000, revenue=3000, target_cpl=60,
        )
        metrics = calculate_metrics(campaign)
        self.assertEqual(metrics["ctr"], 5.0)
        self.assertEqual(metrics["cpl"], 50.0)
        self.assertEqual(metrics["cpo"], 500.0)
        self.assertEqual(metrics["roas"], 3.0)
        self.assertEqual(metrics["qualified_lead_rate"], 50.0)

    def test_loads_fixture_and_adds_metrics(self):
        dataset = load_marketing_dataset(FIXTURE)
        self.assertEqual(len(dataset["campaigns"]), 3)
        self.assertIn("pipeline_roi", dataset["campaigns"][0]["derived_metrics"])

    def test_builds_monthly_payload_without_salesforce(self):
        payload = build_marketing_payload({
            "google_ads": [{
                "report_date": "2026-07-01",
                "campaign_id": "g-1",
                "campaign_name": "Brand",
                "spend": 100,
                "clicks": 20,
                "impressions": 1000,
                "platform_conversions": 4,
            }],
            "linkedin_ads": [],
            "microsoft_ads": [],
            "capterra_ads": [],
        })
        self.assertEqual(payload["salesforce_status"], "not_configured")
        self.assertIsNone(payload["overall_performance"][0]["cpl"])
        self.assertEqual(payload["monthly_performance"][0]["year_month"], "2026-07")

    def test_attributes_salesforce_by_channel_when_campaign_is_missing(self):
        ad_performance = {
            "google_ads": [
                {"report_date": "2026-07-01", "campaign_id": "g-1",
                 "campaign_name": "One", "clicks": 75, "impressions": 1000,
                 "spend": 100, "platform_conversions": 4},
                {"report_date": "2026-07-01", "campaign_id": "g-2",
                 "campaign_name": "Two", "clicks": 25, "impressions": 500,
                 "spend": 50, "platform_conversions": 2},
            ],
            "linkedin_ads": [], "microsoft_ads": [], "capterra_ads": [],
        }
        leads = [
            {"lead_source": "Google Ads", "lead_created_date": "2026-07-10",
             "opportunity_id": "opp-1"},
            {"lead_source": "Google Ads", "lead_created_date": "2026-07-11",
             "opportunity_id": None},
            {"lead_source": "Google Ads", "lead_created_date": "2026-07-12",
             "opportunity_id": None},
            {"lead_source": "Google Ads", "lead_created_date": "2026-07-13",
             "opportunity_id": None},
        ]
        payload = build_marketing_payload(ad_performance, leads)
        by_id = {
            row["campaign_id"]: row for row in payload["overall_performance"]
        }
        self.assertEqual(by_id["g-1"]["total_sf_leads"], 3)
        self.assertEqual(
            by_id["g-1"]["salesforce_attribution_method"],
            "channel_click_share",
        )


class SalesforceMcpTests(unittest.IsolatedAsyncioTestCase):
    async def test_joins_converted_lead_to_opportunity(self):
        lead = {"id": "lead-1", "status": "Qualified",
                "converted_opportunity_id": "opp-1", "utm_campaign": "Search"}
        opportunity = {"id": "opp-1", "stage_name": "Closed Won",
                       "amount": 12000, "is_won": True}
        with patch(
            "marketing_growth_agent.scripts.data_collection_agent.salesforce_mcp._call_tool",
            new=AsyncMock(side_effect=[
                {"records": [lead]}, {"records": [opportunity]}
            ]),
        ):
            records = await fetch_salesforce_funnel(30)
        self.assertEqual(records[0]["opportunity_id"], "opp-1")
        self.assertEqual(records[0]["deal_size"], 12000)
        self.assertTrue(records[0]["is_won"])

    async def test_accepts_cloud_run_leads_and_opportunities_payloads(self):
        lead = {
            "Id": "lead-1",
            "LeadSource": "Google Ads",
            "ConvertedOpportunityId": "opp-1",
            "Industry": "Software",
        }
        opportunity = {
            "Id": "opp-1",
            "StageName": "Proposal",
            "Amount": 25000,
            "Probability": 60,
        }
        with patch(
            "marketing_growth_agent.scripts.data_collection_agent.salesforce_mcp._call_tool",
            new=AsyncMock(side_effect=[
                {"leads": [lead]}, {"opportunities": [opportunity]}
            ]),
        ):
            data = await fetch_salesforce_data(90)
        self.assertEqual(len(data["leads"]), 1)
        self.assertEqual(len(data["opportunities"]), 1)
        self.assertEqual(data["funnel"][0]["opportunity_id"], "opp-1")
        self.assertEqual(data["funnel"][0]["opportunity_probability"], 60)

    async def test_uses_configured_positional_fallback_for_nonmatching_ids(self):
        with patch.dict(
            "os.environ", {"SALESFORCE_POSITIONAL_JOIN_FALLBACK": "true"}
        ), patch(
            "marketing_growth_agent.scripts.data_collection_agent.salesforce_mcp._call_tool",
            new=AsyncMock(side_effect=[
                {"leads": [{
                    "Id": "lead-1",
                    "converted_opportunity_id": "external-1",
                }]},
                {"opportunities": [{
                    "opportunity_id": "internal-1",
                    "current_stage": "Negotiation",
                    "deal_value_arr": 50000,
                }]},
            ]),
        ):
            data = await fetch_salesforce_data(90)
        joined = data["funnel"][0]
        self.assertEqual(joined["opportunity_id"], "internal-1")
        self.assertEqual(joined["opportunity_stage"], "Negotiation")
        self.assertEqual(joined["deal_size"], 50000)
        self.assertEqual(joined["salesforce_join_method"], "position_fallback")


class DecisionTests(unittest.TestCase):
    def test_creates_bounded_approval_proposals(self):
        dataset = load_marketing_dataset(FIXTURE)
        analyses = {"campaigns": [{
            "campaign_id": "linkedin-002", "campaign_health": "critical",
            "analysis_summary": "Lead quality and efficiency declined.",
        }]}
        assessment = {
            "target_attainment": 70,
            "forecasted_pipeline": 1050000,
            "budget_recommendations": [{
                "campaign_id": "linkedin-002", "direction": "decrease",
                "percent": 20, "reason": "CPL exceeds target.",
            }],
            "experiment_recommendations": [{
                "name": "New proof point", "hypothesis": "Proof raises CTR",
                "primary_metric": "ctr", "campaign_ids": ["linkedin-002"],
            }],
        }
        result = evaluate_actions(dataset, analyses, assessment)
        action_types = {action["type"] for action in result["actions"]}
        self.assertIn("growth_review", action_types)
        self.assertIn("campaign_alert", action_types)
        self.assertIn("budget_change", action_types)
        self.assertIn("creative_refresh", action_types)
        self.assertIn("growth_experiment", action_types)
        self.assertTrue(all(action["approval_required"] for action in result["actions"]))

    def test_preserves_full_pause_recommendation(self):
        result = evaluate_actions(
            {"campaigns": []},
            {"campaigns": []},
            {
                "target_attainment": 100,
                "budget_recommendations": [{
                    "campaign_id": "CAP004",
                    "direction": "pause",
                    "percent": 100,
                    "reason": "No conversions",
                }],
            },
        )
        pause = next(
            item for item in result["actions"]
            if item["type"] == "budget_change"
        )
        self.assertEqual(pause["campaign_id"], "CAP004")
        self.assertEqual(pause["payload"]["percent"], 100)

    def test_combines_pipeline_output_by_campaign(self):
        state = {
            "marketing_dataset": {
                "period": "2026-07",
                "pipeline_target": 100000,
                "campaigns": [{
                    "campaign_id": "one",
                    "campaign_name": "Search",
                    "platform": "google_ads",
                    "spend": 1000,
                    "impressions": 10000,
                    "clicks": 500,
                    "conversions": 20,
                    "qualified_leads": 0,
                    "opportunities": 0,
                    "pipeline_value": 0,
                    "revenue": 0,
                    "derived_metrics": {"ctr": 5.0, "cpl": 50.0},
                }],
            },
            "campaign_analysis_results": {"campaigns": [{
                "campaign_id": "one", "campaign_health": "healthy"
            }]},
            "growth_assessment_result": {
                "campaign_assessments": [{
                    "campaign_id": "one",
                    "performance_category": "Top Performers",
                    "growth_outlook": "High",
                }],
                "budget_recommendations": [{
                    "campaign_id": "one", "direction": "increase", "percent": 10
                }],
                "performance_groups": [{
                    "category": "Top Performers", "campaign_ids": ["one"]
                }],
            },
            "marketing_payload": {
                "overall_performance": [{"campaign_id": "one", "cpc": 2.0}],
                "monthly_performance": [{
                    "campaign_id": "one", "year_month": "2026-07"
                }],
            },
            "actions_taken": {"actions": []},
        }
        report = build_campaign_wise_report(state)
        campaign = report["campaign_wise_results"][0]
        self.assertEqual(campaign["performance_category"], "Top Performers")
        self.assertEqual(campaign["analysis"]["campaign_health"], "healthy")
        self.assertEqual(campaign["growth_assessment"]["growth_outlook"], "High")
        self.assertEqual(campaign["monthly_performance"][0]["year_month"], "2026-07")


if __name__ == "__main__":
    unittest.main()
