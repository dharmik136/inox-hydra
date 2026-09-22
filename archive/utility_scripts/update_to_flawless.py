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
FILE_PATH = "motadata_to_enterprise_4k_flawless.jpg"
OLD_DRAFT_ID = "01a09f00-2569-7298-8ed8-40efd7e7e9bb"

with open("draft_post_1.txt", "r", encoding="utf-8") as f:
    post_content = f.read()

# 1. Create fresh draft
req_create = urllib.request.Request(
    "https://api.taplio.com/v1/posts/drafts",
    data=json.dumps({"content": post_content}).encode("utf-8"),
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    method="POST"
)

with urllib.request.urlopen(req_create) as resp:
    new_draft = json.loads(resp.read().decode("utf-8"))
    new_draft_id = new_draft["data"]["id"]
    print("Created fresh draft:", new_draft_id)

# 2. Upload flawless 4K graphic
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
    f"https://api.taplio.com/v1/posts/drafts/{new_draft_id}/upload",
    data=payload,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Mozilla/5.0"
    },
    method="POST"
)

with urllib.request.urlopen(req_upload) as resp:
    upload_res = json.loads(resp.read().decode("utf-8"))
    print("Flawless 4K graphic uploaded to Taplio draft successfully!")

# 3. Delete old botched draft
req_del = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{OLD_DRAFT_ID}",
    headers={"Authorization": f"Bearer {API_KEY}", "User-Agent": "Mozilla/5.0"},
    method="DELETE"
)
try:
    with urllib.request.urlopen(req_del) as resp:
        print("Deleted old draft:", OLD_DRAFT_ID)
except Exception as e:
    print("Old draft delete error:", e)

print(f"\nSUCCESS: Draft {new_draft_id} is now updated in Taplio with the flawless 4K asset!")
