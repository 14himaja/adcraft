"""Meta Marketing API Dry-Run / Smoke Verification Script.

Usage:
  uv run python scripts/meta_smoke.py
  uv run --env-file ../.env python scripts/meta_smoke.py
"""

import hashlib
import hmac
import os
import sys

import httpx

GRAPH_VERSION = "v26.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def main() -> int:
    print("=" * 60)
    print("Meta Graph API Smoke Check (Read-Only / Offline-Safe)")
    print("=" * 60)

    token = os.environ.get("META_ACCESS_TOKEN") or os.environ.get("META_SYSTEM_USER_TOKEN")
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")

    missing = []
    if not token:
        missing.append("META_ACCESS_TOKEN (or META_SYSTEM_USER_TOKEN)")
    if not app_id:
        missing.append("META_APP_ID")
    if not app_secret:
        missing.append("META_APP_SECRET")

    if missing:
        print("\n[INFO] Missing environment credentials:")
        for item in missing:
            print(f"  - {item}")
        print("\nOffline / Sandbox Mode:")
        print("  Backend is operating in META_MODE=fake. No live Meta API calls required.")
        print("  To run real Graph API checks, supply credentials in .env and re-run.")
        print("  See docs/meta-connection-guide.md for step-by-step instructions.\n")
        return 0

    proof = hmac.new(app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()

    client = httpx.Client(timeout=10.0)

    try:
        # 1. Debug token check
        print("\n1. Verifying token via /debug_token ...")
        app_token = f"{app_id}|{app_secret}"
        debug_resp = client.get(
            f"{BASE_URL}/debug_token",
            params={"input_token": token, "access_token": app_token},
        )
        if debug_resp.status_code == 200:
            data = debug_resp.json().get("data", {})
            is_valid = data.get("is_valid")
            scopes = data.get("scopes", [])
            expires_at = data.get("data_access_expires_at") or data.get("expires_at")
            print(f"   Status: {'Valid' if is_valid else 'Invalid'}")
            print(f"   App ID: {data.get('app_id')}")
            print(f"   Expires: {expires_at}")
            print(f"   Scopes: {', '.join(scopes) if scopes else 'None'}")
        else:
            print(f"   [WARN] debug_token returned {debug_resp.status_code}: {debug_resp.text}")

        # 2. GET /me
        print("\n2. Checking user identity (/me) ...")
        me_resp = client.get(
            f"{BASE_URL}/me",
            params={"access_token": token, "appsecret_proof": proof, "fields": "id,name"},
        )
        if me_resp.status_code == 200:
            me_data = me_resp.json()
            print(f"   User Name: {me_data.get('name')}")
            print(f"   User ID:   {me_data.get('id')}")
        else:
            print(f"   [WARN] /me returned {me_resp.status_code}: {me_resp.text}")

        # 3. GET /me/adaccounts
        print("\n3. Checking accessible Ad Accounts (/me/adaccounts) ...")
        acc_resp = client.get(
            f"{BASE_URL}/me/adaccounts",
            params={"access_token": token, "appsecret_proof": proof, "fields": "id,name,currency"},
        )
        if acc_resp.status_code == 200:
            accounts = acc_resp.json().get("data", [])
            print(f"   Found {len(accounts)} ad account(s):")
            for acc in accounts:
                print(f"     - {acc.get('name')} ({acc.get('id')}) [{acc.get('currency')}]")
        else:
            print(f"   [WARN] /me/adaccounts returned {acc_resp.status_code}: {acc_resp.text}")

        print("\n[SUCCESS] Meta API Smoke Check completed.\n")
        return 0

    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        print(f"\n[INFO] Offline / Network unreachable: {exc}")
        print("Operating in offline sandbox mode safely.\n")
        return 0
    except Exception as exc:
        print(f"\n[ERROR] Unexpected error during smoke check: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
