# Marketing Growth Agent

A four-stage Google ADK pipeline that normalizes marketing data, analyzes
campaigns, assesses cross-channel growth, and creates approval-ready actions.

## Run

From the parent repository:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r marketing_growth_agent/requirements.txt
Copy-Item marketing_growth_agent/.env.example marketing_growth_agent/.env
python -m marketing_growth_agent.main
```

Alternatively, from inside the `marketing_growth_agent` directory:

```powershell
python main.py
```

To test only BigQuery and Salesforce collection without running the LLM,
decision, reporting, or email stages:

```powershell
python main.py --data-only
```

By default the collector reads Lead and Opportunity from the Salesforce MCP
server, while ad-platform data remains in the four configured BigQuery tables.
Start the MCP server first (see `salesforce_lead_opportunity_mcp/README.md`) and
set `SALESFORCE_MCP_URL` if it is not at `http://localhost:8080/mcp`. Set
`MARKETING_PIPELINE_TARGET` before running. For local development, set
`MARKETING_DATA_PATH` to a normalized JSON dataset such as the bundled fixture.
Gemini and Google Cloud credentials are required for a full BigQuery run.

Use Python 3.10 or newer (Python 3.11 is recommended). If Salesforce is
temporarily unavailable, set `MARKETING_SALESFORCE_ENABLED=false`; the collector
will publish empty CRM counts and continue with BigQuery campaign data.

For the IAM-protected Cloud Run Salesforce MCP endpoint, use
`MARKETING_SALESFORCE_ENABLED=true`, set `SALESFORCE_MCP_URL`, and authenticate
the local Cloud CLI account with `gcloud auth login`. The client automatically
uses SSE for `/sse` endpoints and Streamable HTTP for `/mcp` endpoints.

The collector publishes:

- `marketing_payload`: overall CPL/CPO/CTR/CPC and monthly trends
- `ad_platform_performance`: raw BigQuery rows grouped by platform
- `crm_funnel_details`: empty until Salesforce is enabled
- `marketing_dataset`: normalized input consumed by downstream agents

The final CLI output is consolidated under `campaign_wise_results`. Each
campaign includes its metrics, monthly history, analysis, budget recommendation,
and proposed actions. Intermediate agent responses are printed by default. Set
`MARKETING_VERBOSE_AGENT_OUTPUT=false` to display only the combined report.

## Gmail notifications

The Decision Action Agent can send:

- a concise portfolio summary and channel forecasts to
  `MARKETING_MANAGER_EMAIL`
- the complete combined campaign report as a JSON attachment to
  `MARKETING_REPORT_EMAIL`

In Google Cloud Console, enable the Gmail API and create an OAuth client of type
**Desktop app**. Download it as `credentials.json` into this directory, then set
the recipient addresses in `.env`. The first `python main.py` run opens a browser
for Gmail consent and stores the reusable token in `gmail_token.json`.

Email errors are included under `actions_taken.notifications` and do not stop
the analysis pipeline. Set `MARKETING_EMAIL_NOTIFICATIONS_ENABLED=false` to
disable sending.

The collector writes `ad_platform_performance`, `crm_funnel_details`, and the
normalized downstream contract `marketing_dataset` into ADK session state.

## Test

```powershell
python -m unittest discover -s marketing_growth_agent/tests -v
```

This MVP creates proposals only. It does not mutate advertising accounts.
