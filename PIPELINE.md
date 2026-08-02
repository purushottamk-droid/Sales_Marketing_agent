# Marketing Growth Agent Pipeline

## Purpose

The pipeline turns cross-channel campaign and CRM performance into grounded
growth recommendations. Arithmetic is deterministic, LLM outputs are typed, and
all proposed changes require approval.

## Flow

```text
Normalized ad + CRM data
          |
          v
MarketingDataCollectionAgent
          |-> ad_platform_performance
          |-> crm_funnel_details
          `-> marketing_dataset
          |
          v
campaign_analysis_agent -> campaign_analysis_results
          |
          v
growth_assessment_agent -> growth_assessment_result
          |
          v
DecisionActionAgent -> actions_taken
```

## State contracts

### `marketing_dataset`

Contains account, reporting period, pipeline target, raw campaign fields, and
Python-calculated CTR, CPC, CPL, qualified-lead rate, opportunity rate, ROAS,
pipeline ROI, and budget utilization.

### `ad_platform_performance`

Contains the date-filtered Google Ads, LinkedIn Ads, Capterra, and Microsoft Ads
rows plus record counts for each source.

### `crm_funnel_details`

Contains Salesforce lead records joined to converted opportunities, including
UTM attribution, deal value, stage, close date, and won status. Its summary
reports total leads, converted opportunities, and won opportunities.

### `campaign_analysis_results`

One typed analysis per campaign: health, efficiency score, growth potential,
high-intent segments, issues, recommendation, and manager summary.

### `growth_assessment_result`

Portfolio forecast, target attainment, growth risk, bounded budget guidance,
priority segments, experiments, and manager-attention flag.

### `actions_taken`

An audit list of `PROPOSED` and `SKIPPED` records. Proposed actions include a
reason, payload, campaign identifier where applicable, and
`approval_required=true`.

## Decision policy

| Condition | Proposal |
|---|---|
| Forecasted pipeline attainment below 80% | Growth review |
| Campaign health is `critical` | Campaign alert |
| Assessment recommends an increase/decrease | Budget change, capped at 20% |
| CTR drops at least 20% and frequency is at least 3 | Creative refresh |
| Experiment has hypothesis, metric, and campaign IDs | Growth experiment |

## BigQuery sources

The collector queries these tables concurrently from
`atgeir-moae-dev.marketing_agent`:

| State source | Default table |
|---|---|
| Google Ads | `google_ads` |
| LinkedIn Ads | `linkedin_ads` |
| Capterra | `capterra` |
| Microsoft Ads | `microsoft_ads` |
| Salesforce opportunities | `Salesforce_Opportunities` |
| Salesforce leads | `Salesforce_Leads` |

Salesforce leads are joined to opportunities using
`ConvertedOpportunityId = opportunity.Id`. The resulting funnel is attributed
to advertising campaigns by matching `utm_campaign__c` to campaign name, with
campaign ID as a fallback.

`MARKETING_PIPELINE_TARGET` is required for BigQuery runs. The optional
`MARKETING_DEFAULT_TARGET_CPL` supplies a fallback when an ad row has no target.
The `lookback_days` session value controls all source filters and defaults to 90
days. Valid values are 1-730.

Live action adapters should be separate from proposal generation. Add an
approval service first, then execute only an approved immutable action record
with spend ceilings, idempotency keys, rollback metadata, and API audit logs.

## Guardrails

- No invented IDs, metrics, targets, or audience evidence.
- No live campaign mutation in this MVP.
- Budget movement is limited to 20% per proposal.
- Lead quality and pipeline are considered alongside platform conversions.
- Forecasts are directional until a statistical forecasting service is added.
- Sensitive-attribute targeting is outside the supported action set.
