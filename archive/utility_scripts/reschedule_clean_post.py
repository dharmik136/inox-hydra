import urllib.request
import urllib.error
import json
import uuid

API_KEY = "01a08fa4-2354-769d-b2a1-86136e7dae52"
FILE_PATH = "motadata_to_enterprise_4k_flawless.jpg"
OLD_POST_ID = "01a09f18-77a6-729b-87ed-b336af47087c"

with open("draft_post_1.txt", "r", encoding="utf-8") as f:
    post_content = f.read()

# 1. Unschedule / Delete old scheduled post
# First unschedule via POST /posts/drafts/{id}/unschedule or delete
req_unsched = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{OLD_POST_ID}/unschedule",
    data=json.dumps({}).encode("utf-8"),
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    method="POST"
)
try:
    with urllib.request.urlopen(req_unsched) as resp:
        print("Unscheduled old post:", OLD_POST_ID)
except Exception as e:
    print("Unschedule attempt note:", e)

# Delete old post
req_del = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{OLD_POST_ID}",
    headers={"Authorization": f"Bearer {API_KEY}", "User-Agent": "Mozilla/5.0"},
    method="DELETE"
)
try:
    with urllib.request.urlopen(req_del) as resp:
        print("Deleted old post draft:", OLD_POST_ID)
except Exception as e:
    print("Delete attempt note:", e)

# 2. Create fresh draft with the new post content
req_create = urllib.request.Request(
    "https://api.taplio.com/v1/posts/drafts",
    data=json.dumps({"content": post_content}).encode("utf-8"),
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    method="POST"
)
with urllib.request.urlopen(req_create) as resp:
    new_draft = json.loads(resp.read().decode("utf-8"))
    new_draft_id = new_draft["data"]["id"]
    print("Created fresh draft with revised content:", new_draft_id)

# 3. Upload the 4K graphic
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
    print("Graphic uploaded!")

# 4. Schedule for 5:30 PM IST (12:00:00 UTC)
req_sched = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{new_draft_id}/schedule",
    data=json.dumps({"scheduled_for": "2026-09-14T12:00:00Z"}).encode("utf-8"),
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    method="POST"
)
with urllib.request.urlopen(req_sched) as resp:
    sched_res = json.loads(resp.read().decode("utf-8"))
    print("New post scheduled successfully:", sched_res.get("data", {}).get("status"), "for", sched_res.get("data", {}).get("scheduled_for"))

print(f"\nALL SET: New Post ID {new_draft_id} is scheduled!")
