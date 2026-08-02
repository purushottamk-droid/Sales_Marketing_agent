# Salesforce Lead + Opportunity MCP Server

A read-only MCP server for exactly two Salesforce objects:

- Lead
- Opportunity

It uses the Salesforce JWT Bearer flow and does not expose arbitrary SOQL.

## 1. Salesforce setup

1. Create or use a Salesforce Connected App.
2. Upload the public certificate under the Connected App digital-signature setting.
3. Enable OAuth/JWT access.
4. Pre-authorize the integration user.
5. Give that user read access to Lead, Opportunity, and every field listed in
   `salesforce_mcp_server/schema.py`.

For a sandbox, use:

- `SALESFORCE_JWT_AUDIENCE=https://test.salesforce.com`
- `SALESFORCE_TOKEN_URL=https://test.salesforce.com/services/oauth2/token`

## 2. Local setup

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`, then start:

```powershell
python -m salesforce_mcp_server.server
```

The Streamable HTTP endpoint is normally:

```text
http://localhost:8080/mcp
```

## 3. Test with MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector
```

Connect the inspector to:

```text
http://localhost:8080/mcp
```

## 4. Available tools

- `get_leads`
- `get_opportunities`
- `get_lead_by_id`
- `get_opportunity_by_id`
- `get_converted_opportunity_for_lead`

## 5. Customize fields

Edit `LEAD_FIELDS` and `OPPORTUNITY_FIELDS` in
`salesforce_mcp_server/schema.py`.

Use exact Salesforce API names. Remove inaccessible or nonexistent fields,
because Salesforce rejects the whole SOQL query when any selected field is
invalid.

## 6. Cloud Run example

```bash
gcloud run deploy salesforce-lead-opportunity-mcp \
  --source . \
  --region us-central1 \
  --no-allow-unauthenticated \
  --set-env-vars SALESFORCE_JWT_CLIENT_ID=YOUR_CLIENT_ID,SALESFORCE_JWT_SUBJECT=YOUR_USERNAME,SALESFORCE_JWT_AUDIENCE=https://login.salesforce.com,SALESFORCE_TOKEN_URL=https://login.salesforce.com/services/oauth2/token,SALESFORCE_API_VERSION=v60.0 \
  --set-secrets SALESFORCE_JWT_PRIVATE_KEY=SALESFORCE_JWT_PRIVATE_KEY:latest
```

Do not place the private key in source control or directly in a deployment
command.
