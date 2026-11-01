import hashlib
import hmac
import json
import sys
import time
import urllib.request

if len(sys.argv) < 3:
    print("Usage: python signed_post.py <META_APP_SECRET> <instagram_user_id> [message_text]")
    sys.exit(1)

SECRET, IG_ID = sys.argv[1], sys.argv[2]
CUSTOMER = "cust_123"
TEXT = " ".join(sys.argv[3:]) if len(sys.argv) > 3 and sys.argv[3:] else "What time do you open?"

body = json.dumps(
    {
        "object": "instagram",
        "entry": [
            {
                "id": IG_ID,
                "time": int(time.time()),
                "messaging": [
                    {
                        "sender": {"id": CUSTOMER},
                        "recipient": {"id": IG_ID},
                        "timestamp": int(time.time() * 1000),
                        "message": {"mid": f"m_{time.time_ns()}", "text": TEXT},
                    }
                ],
            }
        ],
    }
).encode()

sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(
    "http://localhost:8000/webhooks/instagram",
    data=body,
    headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
)

try:
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())
except Exception as e:
    print(f"Error: {e}")
