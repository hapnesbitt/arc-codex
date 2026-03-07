#!/usr/bin/env python3
"""
linkedin_auth.py — One-time OAuth flow to get LinkedIn access token.
Run this once, store the token in backend/.env, then use linkedin_poster.py.

Usage:
    cd /home/www/arc_stack/backend
    python3 linkedin_auth.py

Requires in .env (or set as env vars):
    LINKEDIN_CLIENT_ID=...
    LINKEDIN_CLIENT_SECRET=...
"""

import http.server
import threading
import urllib.parse
import urllib.request
import json
import os
import secrets
import webbrowser
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8765/callback"
SCOPE         = "openid profile w_member_social"

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in backend/.env first")
    exit(1)

# --- Local callback server ---
auth_code = None
state_expected = secrets.token_urlsafe(16)

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            state_got = params.get("state", [None])[0]
            if state_got != state_expected:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch - possible CSRF. Try again.")
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorization complete! You can close this tab.</h2>")
        elif "error" in params:
            self.send_response(400)
            self.end_headers()
            error = params.get("error_description", ["Unknown error"])[0]
            self.wfile.write(f"<h2>Error: {error}</h2>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


def exchange_code_for_token(code):
    data = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()

    req = urllib.request.Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_member_id(access_token):
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        return data.get("sub")  # URN-format member ID


# --- Start local server ---
server = http.server.HTTPServer(("localhost", 8765), CallbackHandler)
server_thread = threading.Thread(target=server.serve_forever)
server_thread.daemon = True
server_thread.start()

# --- Build auth URL ---
params = urllib.parse.urlencode({
    "response_type": "code",
    "client_id":     CLIENT_ID,
    "redirect_uri":  REDIRECT_URI,
    "scope":         SCOPE,
    "state":         state_expected,
})
auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{params}"

print("🔗 Opening LinkedIn authorization in your browser...")
print(f"   If it doesn't open, visit:\n   {auth_url}\n")
webbrowser.open(auth_url)

# --- Wait for callback ---
print("⏳ Waiting for authorization...")
import time
for _ in range(120):  # 2 minute timeout
    if auth_code:
        break
    time.sleep(1)
else:
    print("❌ Timeout — no authorization received.")
    server.shutdown()
    exit(1)

server.shutdown()

# --- Exchange for token ---
print("🔄 Exchanging code for access token...")
try:
    token_data = exchange_code_for_token(auth_code)
except Exception as e:
    print(f"❌ Token exchange failed: {e}")
    exit(1)

access_token  = token_data.get("access_token")
expires_in    = token_data.get("expires_in", "unknown")
refresh_token = token_data.get("refresh_token")

if not access_token:
    print(f"❌ No access token in response: {token_data}")
    exit(1)

# --- Get member ID ---
print("🔍 Fetching your LinkedIn member ID...")
try:
    member_id = get_member_id(access_token)
except Exception as e:
    print(f"⚠️  Could not fetch member ID: {e}")
    member_id = "UNKNOWN"

print()
print("✅ Success! Add these to backend/.env:")
print()
print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
print(f"LINKEDIN_MEMBER_ID={member_id}")
if refresh_token:
    print(f"LINKEDIN_REFRESH_TOKEN={refresh_token}")
print()
print(f"Token expires in: {int(expires_in)//86400} days")
print()
print("⚠️  LinkedIn tokens expire in ~60 days. Re-run this script to refresh.")
