import os
from dotenv import load_dotenv
from stravalib.client import Client

load_dotenv()

# Initialize client
client = Client()
client_id = os.getenv('STRAVA_CLIENT_ID')
client_secret = os.getenv('STRAVA_CLIENT_SECRET')

if not client_id or not client_secret:
    print("Error: Check your .env file for CLIENT_ID and CLIENT_SECRET")
    exit()

# Step 1: Generate Authorization URL
# 'activity:read_all' is required to see private activities and full sensor streams
url = client.authorization_url(
    client_id=client_id,
    redirect_uri='http://localhost:8282',
    scope=['read_all', 'profile:read_all', 'activity:read_all']
)

print(f"\n1. Open this URL in your browser:\n{url}")
print("\n2. Click 'Authorize'.")
print("3. You will be redirected to a 'Page Not Found' (localhost).")
print("4. Look at the URL in your browser's address bar. Copy the text after 'code=' and before '&scope='.")

# Step 2: Exchange code for Token
code = input("\nPaste the 'code' here: ").strip()

token_response = client.exchange_code_for_token(
    client_id=client_id,
    client_secret=client_secret,
    code=code
)

print("\n--- AUTHENTICATION SUCCESSFUL ---")
print(f"Access Token: {token_response['access_token']}")
print(f"Refresh Token: {token_response['refresh_token']}")
print("\nACTION: Copy the Refresh Token into your .env as STRAVA_REFRESH_TOKEN")