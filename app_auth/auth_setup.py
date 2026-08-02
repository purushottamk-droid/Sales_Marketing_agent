from google_auth_oauthlib.flow import InstalledAppFlow
import json
import os

# =========================
# CONFIG
# =========================
CLIENT_SECRET_FILE = "credentials.json"
OUTPUT_FILE = "oauth_final.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    # "https://www.googleapis.com/auth/gmail.readonly",
    # "https://www.googleapis.com/auth/calendar"
]

# =========================
# RUN OAUTH FLOW
# =========================
flow = InstalledAppFlow.from_client_secrets_file(
    CLIENT_SECRET_FILE,
    SCOPES
)

creds = flow.run_local_server(port=8080,prompt="consent",access_type="offline")
# =========================
# LOAD CLIENT CONFIG
# =========================
with open(CLIENT_SECRET_FILE, "r") as f:
    client_config = json.load(f)

# Handle both "installed" and "web" formats
if "installed" in client_config:
    client_data = client_config["installed"]
elif "web" in client_config:
    client_data = client_config["web"]
else:
    raise RuntimeError("Invalid client_secret.json format")

# =========================
# BUILD FINAL JSON
# =========================
final_secret = {
    "access_token": creds.token,
    "refresh_token": creds.refresh_token,
    "client_id": client_data["client_id"],
    "client_secret": client_data["client_secret"],
    "token_uri": client_data.get("token_uri", "https://oauth2.googleapis.com/token")
}

# =========================
# SAVE TO FILE
# =========================
with open(OUTPUT_FILE, "w") as f:
    json.dump(final_secret, f, indent=2)

print("\n✅ OAuth setup complete!")
print(f"📄 Saved final JSON to: {OUTPUT_FILE}")

# =========================
# SAFETY CHECK
# =========================
if not creds.refresh_token:
    print("\n⚠️ WARNING: No refresh_token received.")
    print("👉 You may need to re-run OAuth and ensure offline access.")