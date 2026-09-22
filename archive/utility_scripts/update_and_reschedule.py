import os
import urllib.request
import urllib.error
import json

# Read from the environment, never written here.
#
# This line used to hold the Taplio key as a literal. These scripts are
# tracked, the repository is public, and that key grants create, schedule and
# publish on the owner's real LinkedIn account. It sat in ten files from the
# initial release commit onward.
#
# Removing it here does not undo that. The literal stays reachable in published
# history, so the key itself had to be rotated. This only stops the next one
# from being committed.
API_KEY = os.environ.get("TAPLIO_API_KEY", "")
if not API_KEY:
    raise SystemExit(
        "Set TAPLIO_API_KEY in your environment before running this script. "
        "In PowerShell: $env:TAPLIO_API_KEY = '<your key>'"
    )
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
