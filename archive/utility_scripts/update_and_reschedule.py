import urllib.request
import urllib.error
import json

API_KEY = "01a08fa4-2354-769d-b2a1-86136e7dae52"
DRAFT_ID = "01a09f35-b6ae-7010-bd13-9464e5cbfdb7"
SCHEDULE_TIME = "2026-09-14T12:00:00.000Z"

with open("draft_post_1.txt", "r", encoding="utf-8") as f:
    text = f.read()

# Make sure media tag is included
content_with_media = text.strip() + "\n\n[img:VCeDGkRSLV]"

# 1. Update draft
req_update = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{DRAFT_ID}",
    data=json.dumps({"content": content_with_media}).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    },
    method="PATCH"
)

try:
    with urllib.request.urlopen(req_update) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Draft updated successfully!")
        print("Media attached:", res.get("data", {}).get("media"))
except urllib.error.HTTPError as e:
    print("Update HTTP Error:", e.code, e.read().decode("utf-8"))
    exit(1)
except Exception as e:
    print("Update error:", e)
    exit(1)

# 2. Schedule draft
req_sched = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{DRAFT_ID}/schedule",
    data=json.dumps({"scheduled_for": SCHEDULE_TIME}).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req_sched) as resp:
        sched_res = json.loads(resp.read().decode("utf-8"))
        print("Scheduled successfully!")
        print("Scheduled details:", sched_res)
except urllib.error.HTTPError as e:
    print("Schedule HTTP Error:", e.code, e.read().decode("utf-8"))
    exit(1)
except Exception as e:
    print("Schedule error:", e)
    exit(1)

print("\nALL OPERATIONS COMPLETED SUCCESSFULLY!")
