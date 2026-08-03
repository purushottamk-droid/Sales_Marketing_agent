# from typing import Any, Dict, List

# from google.adk.agents import BaseAgent
# from google.adk.events import Event, EventActions

# from .output_schema import DecisionActionResult
# from marketing_growth_agent.scripts.reporting import build_campaign_wise_report
# from .tools import create_action_proposal, notify_marketing_stakeholders


# def _as_dict(value: Any) -> Dict[str, Any]:
#     if hasattr(value, "model_dump"):
#         return value.model_dump()
#     return value if isinstance(value, dict) else {}


# def evaluate_actions(
#     dataset: Dict[str, Any], analyses: Dict[str, Any], assessment: Dict[str, Any]
# ) -> Dict[str, Any]:
#     """Apply fixed policy and return an auditable proposal list."""
#     dataset, analyses, assessment = map(_as_dict, (dataset, analyses, assessment))
#     actions: List[Dict[str, Any]] = []

#     attainment = assessment.get("target_attainment", 0)
#     if attainment < 80:
#         actions.append(create_action_proposal(
#             "growth_review", f"Forecast target attainment is {attainment}%, below 80%.",
#             forecasted_pipeline=assessment.get("forecasted_pipeline"),
#         ))
#     else:
#         actions.append({
#             "type": "growth_review", "status": "SKIPPED", "campaign_id": None,
#             "reason": f"Target attainment is {attainment}%, meeting the 80% threshold.",
#             "approval_required": True, "payload": {},
#         })

#     for campaign in analyses.get("campaigns", []):
#         campaign = _as_dict(campaign)
#         if campaign.get("campaign_health") == "critical":
#             actions.append(create_action_proposal(
#                 "campaign_alert",
#                 f"Campaign is critical: {campaign.get('analysis_summary', '')}",
#                 campaign.get("campaign_id"),
#             ))

#     for recommendation in assessment.get("budget_recommendations", []):
#         recommendation = _as_dict(recommendation)
#         requested_percent = max(int(recommendation.get("percent", 0)), 0)
#         percent = (
#             min(requested_percent, 100)
#             if recommendation.get("direction") == "pause"
#             else min(requested_percent, 20)
#         )
#         if recommendation.get("direction") != "hold" and percent:
#             actions.append(create_action_proposal(
#                 "budget_change", recommendation.get("reason", "Budget optimization"),
#                 recommendation.get("campaign_id"), direction=recommendation.get("direction"),
#                 percent=percent,
#             ))

#     raw_by_id = {item["campaign_id"]: item for item in dataset.get("campaigns", [])}
#     for campaign_id, campaign in raw_by_id.items():
#         metrics = campaign.get("derived_metrics", {})
#         current_ctr = metrics.get("ctr", 0)
#         previous_ctr = campaign.get("previous_ctr", 0)
#         ctr_drop = ((previous_ctr - current_ctr) / previous_ctr * 100) if previous_ctr else 0
#         if ctr_drop >= 20 and campaign.get("frequency", 0) >= 3:
#             actions.append(create_action_proposal(
#                 "creative_refresh",
#                 f"CTR fell {ctr_drop:.1f}% while frequency reached {campaign['frequency']}.",
#                 campaign_id, primary_metric="ctr",
#             ))

#     for experiment in assessment.get("experiment_recommendations", []):
#         experiment = _as_dict(experiment)
#         if all(experiment.get(key) for key in ("hypothesis", "primary_metric", "campaign_ids")):
#             actions.append(create_action_proposal(
#                 "growth_experiment", experiment.get("hypothesis", ""),
#                 campaign_ids=experiment["campaign_ids"], name=experiment.get("name"),
#                 primary_metric=experiment["primary_metric"],
#             ))

#     return DecisionActionResult(actions=actions).model_dump()


# class DecisionActionAgent(BaseAgent):
#     async def _run_async_impl(self, ctx):
#         actions_taken = evaluate_actions(
#             ctx.session.state.get("marketing_dataset", {}),
#             ctx.session.state.get("campaign_analysis_results", {}),
#             ctx.session.state.get("growth_assessment_result", {}),
#         )
#         report_state = dict(ctx.session.state)
#         report_state["actions_taken"] = actions_taken
#         report = build_campaign_wise_report(report_state)
#         actions_taken["notifications"] = await notify_marketing_stakeholders(report)
#         ctx.session.state["actions_taken"] = actions_taken
#         yield Event(
#             author=self.name,
#             content=None,
#             actions=EventActions(state_delta={"actions_taken": actions_taken}),
#         )


from google.adk.agents import LlmAgent
from google.genai import types
from .prompt import ACTION_PROMPT
from .tools import notify_manager_tool, notify_report_tool

decision_action_agent = LlmAgent(
    name="decision_action_agent",
    model="gemini-2.5-flash",
    instruction=ACTION_PROMPT,
    tools=[notify_manager_tool, notify_report_tool],
    output_key="decision_action_results",
    include_contents="none",
    generate_content_config=types.GenerateContentConfig(
        max_output_tokens=65536,
    ),
)