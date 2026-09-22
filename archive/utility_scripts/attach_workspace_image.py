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
DRAFT_ID = "01a09e97-a657-7745-af76-16bc77d8a4bb"
FILE_PATH = "deloitte_sap_consulting_workspace_4k.jpg"

boundary = uuid.uuid4().hex
with open(FILE_PATH, "rb") as f:
    file_bytes = f.read()

part_header = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="deloitte_sap_consulting_workspace_4k.jpg"\r\n'
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

try:
    with urllib.request.urlopen(req_upload) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Media uploaded successfully to Taplio draft!")
        print("Draft ID:", res.get("data", {}).get("id"))
        print("Media array:", res.get("data", {}).get("media"))
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}:", e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
