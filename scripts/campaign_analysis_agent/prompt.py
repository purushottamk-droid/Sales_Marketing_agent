import json


def CAMPAIGN_ANALYSIS_PROMPT(ctx) -> str:
    dataset = ctx.state.get("marketing_dataset", {})
    return f"""
You are a performance marketing analyst. Analyze every campaign in the
normalized dataset below and return one structured result per campaign.

DATASET:
{json.dumps(dataset, indent=2, default=str)}

Use only supplied evidence. Do not recalculate derived_metrics and do not invent
benchmarks. Evaluate efficiency against target_cpl, lead quality, opportunity
creation, ROAS, pipeline ROI, budget utilization, CTR movement, frequency, and
the supplied audience segment results.

Health guidance:
- healthy: efficient, good downstream quality, and no material warning
- watch: early deterioration or a single moderate issue
- at_risk: target miss or weak downstream quality requiring intervention
- critical: severe waste, collapse, or multiple material issues

Efficiency score is 0-100 and must be justified by the supplied evidence.
High-intent segments require direct segment-level evidence. Keep the summary to
2-3 sentences and recommend one concrete next action. Return every campaign.
"""
