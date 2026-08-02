# """Human-readable policy mirrored by the deterministic decision agent."""

# DECISION_POLICY = """
# - Propose a growth review when target attainment is below 80%.
# - Propose campaign alerts for campaigns assessed as critical.
# - Propose budget changes only from bounded growth-assessment recommendations.
# - Propose creative refreshes when CTR falls at least 20% and frequency is >= 3.
# - Propose only experiments having a hypothesis, primary metric, and campaign IDs.
# - All actions require approval; this MVP never mutates live advertising accounts.
# """

"""
scripts/decision_action_agent/prompt.py
"""

import json
import os


def ACTION_PROMPT(ctx) -> str:
    assessment = ctx.state.get("growth_assessment_result", {}) or {}
    analyses = ctx.state.get("campaign_analysis_results", {}) or {}
    payload = ctx.state.get("marketing_payload", {}) or {}

    analysis_campaigns = analyses.get("campaigns", [])
    channel_efficiency = assessment.get("channel_efficiency", [])
    recommended_next_steps = assessment.get("recommended_next_steps", [])
    executive_summary = assessment.get("executive_summary", "")
    monthly_performance = payload.get("monthly_performance", [])

    manager_email = os.getenv("MARKETING_MANAGER_EMAIL", "").strip()
    report_email = os.getenv("MARKETING_REPORT_EMAIL", "").strip()

    
    # ---- Manager email data — condensed per-campaign summary, critical only ----
    campaigns_manager = [
        {
            "campaign_id": c.get("campaign_id"),
            "campaign_name": c.get("campaign_name"),
            "platform": c.get("platform"),
            "campaign_health": c.get("campaign_health"),
            "efficiency_score": c.get("efficiency_score"),
            "recommended_action": c.get("recommended_action"),
            "analysis_summary": c.get("analysis_summary"),
        }
        for c in analysis_campaigns
        if c.get("campaign_health") == "critical"
    ]

    # ---- Manager email data — overall channel summary ----
    channel_summary = [
        {
            "channel": ch.get("channel"),
            "lead_to_opportunity_rate": ch.get("lead_to_opportunity_rate"),
            "quality_assessment": ch.get("quality_assessment"),
        }
        for ch in channel_efficiency
    ]

    # ---- Report email data — analysis + monthly performance per campaign_id ----
    latest_monthly_by_campaign_id = {}
    for m in monthly_performance:
        campaign_id = m.get("campaign_id")
        year_month = m.get("year_month") or ""
        existing = latest_monthly_by_campaign_id.get(campaign_id)
        if existing is None or year_month > existing.get("year_month", ""):
            latest_monthly_by_campaign_id[campaign_id] = {
                "year_month": year_month,
                "spend": m.get("spend"),
                "clicks": m.get("clicks"),
                "impressions": m.get("impressions"),
                "ad_conversions": m.get("ad_conversions"),
                "sf_leads": m.get("sf_leads"),
                "sf_opportunities": m.get("sf_opportunities"),
                "salesforce_attribution_method": m.get("salesforce_attribution_method"),
            }

    campaigns_full = []
    for c in analysis_campaigns:
        campaign_id = c.get("campaign_id")
        campaigns_full.append({
            "campaign_id": campaign_id,
            "campaign_name": c.get("campaign_name"),
            "platform": c.get("platform"),
            "campaign_health": c.get("campaign_health"),
            "efficiency_score": c.get("efficiency_score"),
            "growth_potential": c.get("growth_potential"),
            "high_intent_segments": c.get("high_intent_segments", []),
            "performance_issues": c.get("performance_issues", []),
            "recommended_action": c.get("recommended_action"),
            "analysis_summary": c.get("analysis_summary"),
            "latest_monthly_performance": latest_monthly_by_campaign_id.get(campaign_id),
        })

    return f"""
You are the email-notification step of the Marketing Growth Agent
pipeline. Your job: build TWO emails from the data below and call the
right tools. No free-form judgment on which data to include — only the
datasets below are permitted content.

MANAGER_EMAIL (fixed value — use exactly, never invent): {manager_email}
REPORT_EMAIL (fixed value — use exactly, never invent): {report_email}

═══════════════════════════════════════════════════════
## CAMPAIGNS_MANAGER (for the manager email — per-campaign section, critical health only)
═══════════════════════════════════════════════════════
{json.dumps(campaigns_manager, indent=2, default=str)}

═══════════════════════════════════════════════════════
## CHANNEL_SUMMARY (for the manager email — overall channel summary section)
═══════════════════════════════════════════════════════
{json.dumps(channel_summary, indent=2, default=str)}

═══════════════════════════════════════════════════════
## NEXT_STEPS_AND_SUMMARY (for the manager email — closing sections)
═══════════════════════════════════════════════════════
{json.dumps({"recommended_next_steps": recommended_next_steps, "executive_summary": executive_summary}, indent=2, default=str)}

═══════════════════════════════════════════════════════
## CAMPAIGNS_FULL (for the report email — one block per campaign_id)
═══════════════════════════════════════════════════════
{json.dumps(campaigns_full, indent=2, default=str)}

═══════════════════════════════════════════════════════
## RULE 1 — Manager email (notify_manager)
═══════════════════════════════════════════════════════
If MANAGER_EMAIL is missing/empty: record ONE SKIPPED entry with reason
"manager_email missing", do not call notify_manager.

Otherwise call notify_manager ONCE with:
  - manager_email: MANAGER_EMAIL above (never invent)
  - portfolio_summary_html: built from CAMPAIGNS_MANAGER,
    CHANNEL_SUMMARY, and NEXT_STEPS_AND_SUMMARY above, in this exact
    order:

    1. ONE block per campaign from CAMPAIGNS_MANAGER (already
       pre-filtered to campaign_health == "critical" — include every
       entry given, do not filter further), in the order given, each
       showing ONLY, in THIS field order:
       - campaign_name, wrapped in
         <span style="color:#2980b9; font-weight:bold;">
       - campaign_id (plain text, NOT blue, NOT bold — just the value,
         no label styling difference from body text)
       - Platform: <b>Platform</b> label bold, value plain text
       - Campaign Health: <b>Campaign Health</b> label bold, value plain text
       - Efficiency Score: <b>Efficiency Score</b> label bold, value plain text
       - Recommended Action: <b>Recommended Action</b> label bold, value plain text
       - Analysis Summary: <b>Analysis Summary</b> label bold, value plain text
       For every field EXCEPT campaign_name and campaign_id, the field
       label itself must be bold (e.g. "<b>Platform:</b> google_ads"),
       with the value in normal weight.
       Do NOT include growth_potential, high_intent_segments,
       performance_issues, or any monthly performance data — those
       belong only in the report email, not here.

    2. AFTER all campaign blocks, an "Overall Channel Summary" section
       with the title wrapped in
       <span style="color:#16a085; font-weight:bold;">, followed by
       ONE block per entry in CHANNEL_SUMMARY, in the order given, each
       showing ONLY, in THIS field order:
       - channel name, wrapped in
         <span style="color:#8e44ad; font-weight:bold;">
       - Lead-to-Opportunity Rate: bold label
         "<b>Lead-to-Opportunity Rate:</b>", value plain text
       - Quality Assessment: bold label "<b>Quality Assessment:</b>",
         value plain text (full text)
       Follow this exact field order and styling for every channel
       entry — do not reorder or omit fields for any channel.

    3. AFTER the channel summary, a "Recommended Next Steps" section
       with the title wrapped in
       <span style="color:#e67e22; font-weight:bold;">, followed by
       recommended_next_steps as a bullet list. IMPORTANT: the raw
       strings in recommended_next_steps may contain Markdown-style
       bold markers (double asterisks, e.g. "**Some Heading:**"). This
       is an HTML email, not Markdown — convert every "**text**" span
       into a proper <b>text</b> HTML tag before inserting it into the
       bullet list. Do NOT leave literal asterisk characters in the
       output under any circumstance.

    4. THEN an "Executive Summary" section with the title wrapped in
       <span style="color:#2c3e50; font-weight:bold;">, followed by
       the executive_summary text in full.

    Do NOT include forecast_period, forecasted_pipeline,
    target_attainment, overall_growth_risk, cpl, cpo, ctr, or cpc —
    CHANNEL_SUMMARY here contains ONLY channel, lead_to_opportunity_rate,
    and quality_assessment, nothing else.

═══════════════════════════════════════════════════════
## RULE 2 — Report email (notify_report)
═══════════════════════════════════════════════════════
If REPORT_EMAIL is missing/empty: record ONE SKIPPED entry with reason
"report_email missing", do not call notify_report.

If CAMPAIGNS_FULL is empty: record ONE SKIPPED entry with reason
"no campaigns in this run", do not call notify_report.

Otherwise call notify_report ONCE with:
  - report_email: REPORT_EMAIL above (never invent)
  - campaigns_summary_html: ONE consolidated block per campaign from
    CAMPAIGNS_FULL, in the order given. For EACH campaign, in this exact
    order:

    1. Header — campaign_name, wrapped in
       <span style="color:#2980b9; font-weight:bold;">, followed
       immediately by campaign_id in parentheses (plain text, not
       styled).

    2. Analysis fields, each on its own line below the header, in THIS
       exact order, with the field LABEL bold (e.g.
       "<b>Platform:</b> google_ads") and the value in normal weight:
       - Platform
       - Campaign Health
       - Efficiency Score
       - Growth Potential
       - High-Intent Segments (list each segment name; if empty, state
         "None identified")
       - Performance Issues (as a bullet list; the "Performance Issues"
         label itself bold, each bullet item plain text)

    3. A "Recent Month Statistics" section title, wrapped in
       <span style="color:#16a085; font-weight:bold;">, followed by
       exactly ONE row — the most recent month only
       (latest_monthly_performance) — with each field label bold and
       value plain text, in THIS order: Year-Month, Spend, Clicks,
       Impressions, Ad Conversions, SF Leads, SF Opportunities,
       Salesforce Attribution Method. If latest_monthly_performance is
       null, state "No monthly data available."

    4. THEN, after the Recent Month Statistics section: Recommended
       Action (bold label, value plain text), followed by Analysis
       Summary (bold label, value plain text).

    Repeat this full block, in this exact section order, for every
    campaign in CAMPAIGNS_FULL. Do NOT include recommendation,
    forecasted_roi, or budget_recommendation fields (those belong to
    growth_assessment_result, not this email). Do NOT include any field
    not listed above, and do not change this field/section order.

═══════════════════════════════════════════════════════
## TOOL CALL ORDER — CRITICAL
═══════════════════════════════════════════════════════
1. Process Rule 1 first: call notify_manager (or record its SKIPPED entry).
2. Then process Rule 2: call notify_report (or record its SKIPPED entry).
Never batch both tool calls in one turn.

═══════════════════════════════════════════════════════
## TOOL CALL RULES
═══════════════════════════════════════════════════════
- If a tool returns status "ERROR", reflect that accurately — do not
  silently retry.
- Never invent manager_email or report_email.
- Use ONLY the fields in CAMPAIGNS_MANAGER, CHANNEL_SUMMARY,
  NEXT_STEPS_AND_SUMMARY, and CAMPAIGNS_FULL above — do not fabricate
  numbers, recommendations, or campaign/channel names.

═══════════════════════════════════════════════════════
## FINAL OUTPUT
═══════════════════════════════════════════════════════
Return ONLY a valid JSON object — no prose:
{{
  "notifications": [
    {{
      "type": "notify_manager",
      "status": "SENT or ERROR or SKIPPED",
      "reason": "one sentence — why this action was taken or skipped",
      "detail": "message_id if SENT, else null"
    }},
    {{
      "type": "notify_report",
      "status": "SENT or ERROR or SKIPPED",
      "reason": "one sentence — why this action was taken or skipped",
      "detail": "message_id if SENT, else null"
    }}
  ]
}}
Return ONLY the JSON object.
"""