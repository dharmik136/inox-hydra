import os
import urllib.request
import urllib.error
import json
import uuid

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
FILE_PATH = "motadata_to_enterprise_4k_flawless.jpg"

# 1. Upload 4K Graphic
boundary = uuid.uuid4().hex
with open(FILE_PATH, "rb") as f:
    file_bytes = f.read()

part_header = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="motadata_to_enterprise_4k_flawless.jpg"\r\n'
    f"Content-Type: image/jpeg\r\n\r\n"
).encode("utf-8")
part_footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
payload = part_header + file_bytes + part_footer

req_upload = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{DRAFT_ID}/upload",
    data=payload,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Mozilla/5.0"
    },
    method="POST"
)

print("Uploading 4K graphic to draft...")
with urllib.request.urlopen(req_upload, timeout=60) as resp:
    res_upload = json.loads(resp.read().decode("utf-8"))
    print("Graphic uploaded successfully!")
    print("Media:", res_upload.get("data", {}).get("media"))

# 2. Schedule draft for 5:30 PM IST (12:00:00 UTC)
req_sched = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{DRAFT_ID}/schedule",
    data=json.dumps({"scheduled_for": "2026-09-14T12:00:00Z"}).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    },
    method="POST"
)

print("Scheduling post for 5:30 PM IST...")
with urllib.request.urlopen(req_sched, timeout=30) as resp:
    res_sched = json.loads(resp.read().decode("utf-8"))
    print("Post scheduled successfully!")
    print("Status:", res_sched.get("data", {}).get("status"))
    print("Scheduled for:", res_sched.get("data", {}).get("scheduled_for"))

print("\nSUCCESS: Draft is scheduled with flawless 4K asset!")
