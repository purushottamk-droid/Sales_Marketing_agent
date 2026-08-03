# import asyncio
# import base64
# import html
# import json
# import os
# from email.message import EmailMessage
# from email.mime.text import MIMEText
# from pathlib import Path
# from typing import Any, Dict, Optional


# def create_action_proposal(
#     action_type: str,
#     reason: str,
#     campaign_id: Optional[str] = None,
#     **payload: Any,
# ) -> Dict[str, Any]:
#     """Create an auditable proposal without mutating an advertising account."""
#     return {
#         "type": action_type,
#         "status": "PROPOSED",
#         "campaign_id": campaign_id,
#         "reason": reason,
#         "approval_required": True,
#         "payload": payload,
#     }


# GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


# def _build_mime_email(to: str, subject: str, body_html: str) -> str:
#     """Encode a MIME HTML email as a base64url string for the Gmail API."""
#     message = MIMEText(body_html, "html", "utf-8")
#     message["To"] = to
#     message["Subject"] = subject
#     return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


# def _resolve_path(value: str) -> Path:
#     path = Path(value).expanduser()
#     return path if path.is_absolute() else Path.cwd() / path


# def build_gmail_service():
#     """Create an authorized Gmail service using a desktop OAuth client."""
#     from google.auth.transport.requests import Request
#     from google.oauth2.credentials import Credentials
#     from google_auth_oauthlib.flow import InstalledAppFlow
#     from googleapiclient.discovery import build

#     credentials_file = os.getenv("GMAIL_OAUTH_CLIENT_FILE", "credentials.json")
#     token_file = _resolve_path(os.getenv("GMAIL_TOKEN_FILE", "gmail_token.json"))
#     credentials = None
#     if token_file.exists():
#         credentials = Credentials.from_authorized_user_file(
#             str(token_file), GMAIL_SCOPES
#         )
#     if credentials and credentials.expired and credentials.refresh_token:
#         credentials.refresh(Request())
#     if not credentials or not credentials.valid:
#         client_file = _resolve_path(credentials_file)
#         if not client_file.exists():
#             raise FileNotFoundError(
#                 f"Gmail OAuth client file not found: {client_file}"
#             )
#         flow = InstalledAppFlow.from_client_secrets_file(
#             str(client_file), GMAIL_SCOPES
#         )
#         credentials = flow.run_local_server(port=0)
#         token_file.parent.mkdir(parents=True, exist_ok=True)
#         token_file.write_text(credentials.to_json(), encoding="utf-8")
#     return build("gmail", "v1", credentials=credentials, cache_discovery=False)


# def _send_email(
#     recipient: str,
#     subject: str,
#     body_html: str,
#     *,
#     attachment_name: Optional[str] = None,
#     attachment_content: Optional[str] = None,
# ) -> Dict[str, Any]:
#     if not attachment_name or attachment_content is None:
#         raw = _build_mime_email(recipient, subject, body_html)
#     else:
#         message = EmailMessage()
#         message["To"] = recipient
#         message["Subject"] = subject
#         message.set_content("This message contains an HTML marketing report.")
#         message.add_alternative(body_html, subtype="html")
#         message.add_attachment(
#             attachment_content.encode("utf-8"),
#             maintype="application",
#             subtype="json",
#             filename=attachment_name,
#         )
#         raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
#     return (
#         build_gmail_service()
#         .users()
#         .messages()
#         .send(userId="me", body={"raw": raw})
#         .execute()
#     )


# def _manager_email_html(report: Dict[str, Any]) -> str:
#     portfolio = report.get("portfolio_summary", {})
#     forecasts = portfolio.get("channel_forecasts") or []
#     forecast_rows = "".join(
#         "<tr>"
#         f"<td>{html.escape(str(item.get('channel', '')))}</td>"
#         f"<td>{item.get('projected_pipeline_value', 0)}</td>"
#         f"<td>{item.get('forecasted_roi', 0)}</td>"
#         f"<td>{html.escape(str(item.get('assumptions', '')))}</td>"
#         "</tr>"
#         for item in forecasts
#     ) or '<tr><td colspan="4">No channel forecast is available.</td></tr>'
#     next_steps = "".join(
#         f"<li>{html.escape(str(step))}</li>"
#         for step in portfolio.get("recommended_next_steps") or []
#     )
#     return f"""
#     <html><body style="font-family:Arial,sans-serif;color:#243447">
#       <h2>Marketing Growth Portfolio Brief</h2>
#       <p>{html.escape(str(portfolio.get("executive_summary") or "No summary available."))}</p>
#       <ul>
#         <li><b>Forecast period:</b> {html.escape(str(portfolio.get("forecast_period")))}</li>
#         <li><b>Forecasted pipeline:</b> {portfolio.get("forecasted_pipeline", 0)}</li>
#         <li><b>Target attainment:</b> {portfolio.get("target_attainment", 0)}%</li>
#         <li><b>Growth risk:</b> {html.escape(str(portfolio.get("overall_growth_risk")))}</li>
#       </ul>
#       <h3>Channel Forecasts</h3>
#       <table border="1" cellpadding="7" cellspacing="0">
#         <tr><th>Channel</th><th>Projected Pipeline</th><th>Forecasted ROI</th><th>Assumptions</th></tr>
#         {forecast_rows}
#       </table>
#       <h3>Recommended Next Steps</h3><ul>{next_steps}</ul>
#     </body></html>
#     """


# async def notify_marketing_stakeholders(report: Dict[str, Any]) -> list[dict]:
#     """Email the manager summary and full JSON report to configured recipients."""
#     enabled = os.getenv(
#         "MARKETING_EMAIL_NOTIFICATIONS_ENABLED", "true"
#     ).strip().casefold() in {"1", "true", "yes", "on"}
#     if not enabled:
#         return [{"type": "email_notifications", "status": "SKIPPED",
#                  "reason": "MARKETING_EMAIL_NOTIFICATIONS_ENABLED is false"}]

#     manager_email = os.getenv("MARKETING_MANAGER_EMAIL", "").strip()
#     report_email = os.getenv("MARKETING_REPORT_EMAIL", "").strip()
#     if not manager_email and not report_email:
#         return [{"type": "email_notifications", "status": "SKIPPED",
#                  "reason": "No manager or report recipient email configured"}]

#     notifications = []
#     if manager_email:
#         try:
#             sent = await asyncio.to_thread(
#                 _send_email,
#                 manager_email,
#                 "Marketing Growth Portfolio Summary",
#                 _manager_email_html(report),
#             )
#             notifications.append({
#                 "type": "manager_summary_email", "status": "SENT",
#                 "recipient": manager_email, "message_id": sent.get("id"),
#             })
#         except Exception as exc:
#             notifications.append({
#                 "type": "manager_summary_email", "status": "ERROR",
#                 "recipient": manager_email, "error_message": str(exc),
#             })

#     if report_email:
#         try:
#             report_json = json.dumps(report, indent=2, default=str)
#             sent = await asyncio.to_thread(
#                 _send_email,
#                 report_email,
#                 "Complete Marketing Growth Campaign Report",
#                 "<html><body><h2>Complete Marketing Growth Report</h2>"
#                 "<p>The complete campaign-wise pipeline output is attached as JSON.</p>"
#                 "</body></html>",
#                 attachment_name="marketing_growth_report.json",
#                 attachment_content=report_json,
#             )
#             notifications.append({
#                 "type": "complete_report_email", "status": "SENT",
#                 "recipient": report_email, "message_id": sent.get("id"),
#             })
#         except Exception as exc:
#             notifications.append({
#                 "type": "complete_report_email", "status": "ERROR",
#                 "recipient": report_email, "error_message": str(exc),
#             })
#     return notifications


import base64
from email.mime.text import MIMEText
from typing import Any, Dict, Optional
from marketing_growth_agent.app_auth.auth import build_gmail_service

from google.adk.tools import FunctionTool, ToolContext


def _build_mime_email(to: str, subject: str, body_html: str) -> str:
    message = MIMEText(body_html, "html", "utf-8")
    message["To"] = to
    message["Subject"] = subject
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


# ---------------------------------------------------------------------
# TOOL 1 — Notify manager (portfolio summary only)
# ---------------------------------------------------------------------

async def notify_manager(
    manager_email: str,
    portfolio_summary_html: str,
    tool_context: ToolContext,
) -> dict:
    """Send ONE email to the manager: critical-health campaigns, then an
    overall channel summary, then next steps and an executive summary.

    portfolio_summary_html must be pre-formatted by the prompt layer, in
    this order:
      1. One block per campaign with campaign_health == "critical" only
         (from campaign_analysis_results), each containing ONLY
         campaign_name, campaign_id, platform, campaign_health,
         efficiency_score, recommended_action, and analysis_summary.
      2. An "Overall Channel Summary" section (from
         growth_assessment_result.channel_efficiency), showing ONLY
         channel, lead_to_opportunity_rate, and quality_assessment per
         channel, in that exact order.
      3. A "Recommended Next Steps" section (from growth_assessment_result
         .recommended_next_steps), as a bullet list.
      4. An "Executive Summary" section (from growth_assessment_result
         .executive_summary).

    No growth_potential, high_intent_segments, performance_issues,
    monthly performance data, cpl, cpo, ctr, cpc, or
    lead_to_opportunity_rate belongs in this email.

    manager_email MUST come from session state — never invented or guessed.
    """
    subject = "Marketing Growth Portfolio Summary"
    body_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#243447">
      <h2>Marketing Growth Portfolio Brief</h2>
      {portfolio_summary_html}
    </body></html>
    """
    try:
        service = build_gmail_service()
        raw = _build_mime_email(manager_email, subject, body_html)
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {
            "status": "SENT", "type": "notify_manager",
            "manager_email": manager_email, "message_id": sent.get("id"),
        }
    except Exception as e:
        return {
            "status": "ERROR", "type": "notify_manager",
            "manager_email": manager_email, "error_message": str(e),
        }


# ---------------------------------------------------------------------
# TOOL 2 — Notify report recipient (per-campaign detail only)
# ---------------------------------------------------------------------

async def notify_report(
    report_email: str,
    campaigns_summary_html: str,
    tool_context: ToolContext,
) -> dict:
    """Send ONE consolidated email with one block PER campaign to the report recipient.

    campaigns_summary_html must be pre-formatted by the prompt layer. For
    EACH campaign_id, in this exact order:
      1. Header: campaign_name, bold/highlighted, followed by campaign_id
         in parentheses (plain text).
      2. Analysis fields (from campaign_analysis_results), bold labels:
         platform, campaign_health, efficiency_score, growth_potential,
         high_intent_segments, performance_issues.
      3. A "Recent Month Statistics" section title (distinctly colored),
         followed by exactly ONE row — the latest available month for
         that campaign_id (from marketing_payload.monthly_performance):
         year_month, spend, clicks, impressions, ad_conversions,
         sf_leads, sf_opportunities, salesforce_attribution_method — all
         with bold field labels.
      4. Recommended_action, then analysis_summary — both with bold
         labels, placed AFTER the Recent Month Statistics section.

    Repeat this full block for every campaign_id, all in one email, in
    the order the campaigns were given, preserving this exact section
    order. No other fields, and no growth_assessment_result data
    (recommendation, forecasted_roi, budget_recommendations), belong in
    this email.

    report_email MUST come from session state — never invented or guessed.
    """
    subject = "Marketing Growth Campaign Action Report"
    body_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#243447">
      <h2>Marketing Growth — Campaign Action Report</h2>
      {campaigns_summary_html}
    </body></html>
    """
    try:
        service = build_gmail_service()
        raw = _build_mime_email(report_email, subject, body_html)
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {
            "status": "SENT", "type": "notify_report",
            "report_email": report_email, "message_id": sent.get("id"),
        }
    except Exception as e:
        return {
            "status": "ERROR", "type": "notify_report",
            "report_email": report_email, "error_message": str(e),
        }


notify_manager_tool = FunctionTool(func=notify_manager)
notify_report_tool = FunctionTool(func=notify_report)