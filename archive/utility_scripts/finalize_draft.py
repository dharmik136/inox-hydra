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
DRAFT_ID = "01a08fd1-da14-75fa-a970-6a83144f078d"

final_content = """𝗭𝗲𝗿𝗼 𝗺𝗮𝗻𝘂𝗮𝗹 𝗶𝗻𝘁𝗲𝗿𝘃𝗲𝗻𝘁𝗶𝗼𝗻.

That is the only AI metric that actually matters.

Not how many slides your team made.
Not which frontier model you pay for.
And definitely not how fast someone types prompts into ChatGPT.

Here is the hard truth:

If you have to prompt your AI 10 times to finish a single task, you didn’t automate work.

You just gave yourself a new full-time babysitting job.

𝗧𝗵𝗲 𝗼𝘂𝘁𝗰𝗼𝗺𝗲 𝘁𝗵𝗲 𝘁𝗼𝗽 𝟭𝟬% 𝗮𝗿𝗲 𝗮𝗰𝘁𝘂𝗮𝗹𝗹𝘆 𝗯𝘂𝗶𝗹𝗱𝗶𝗻𝗴:

━━━━━━━━━━━━━━━━━━━━━

𝟭. 𝗙𝗿𝗼𝗺 𝗖𝗵𝗮𝘁 𝗕𝗼𝘅𝗲𝘀 → 𝗧𝗼 𝗜𝗻𝘃𝗶𝘀𝗶𝗯𝗹𝗲 𝗜𝗻𝗳𝗿𝗮𝘀𝘁𝗿𝘂𝗰𝘁𝘂𝗿𝗲
Chat windows are pure manual friction.
You open them. You wait. You copy. You paste.
𝘙𝘦𝘢𝘭 𝘭𝘦𝘷𝘦𝘳𝘢𝘨𝘦 𝘩𝘢𝘱𝘱𝘦𝘯𝘴 𝘪𝘯 𝘵𝘩𝘦 𝘣𝘢𝘤𝘬𝘨𝘳𝘰𝘶𝘯𝘥:
• A webhook triggers
• The agent executes
• The database updates
Zero tabs opened. Zero manual steps.

𝟮. 𝗙𝗿𝗼𝗺 "𝗗𝗼 𝗘𝘃𝗲𝗿𝘆𝘁𝗵𝗶𝗻𝗴" → 𝗧𝗼 𝗦𝘁𝗿𝗶𝗰𝘁 𝗕𝗼𝘂𝗻𝗱𝗮𝗿𝗶𝗲𝘀
Vague prompts cause hallucinations.
Models don't fail because they are dumb.
They fail because they have no guardrails.
Break the job into small, deterministic steps:
→ Extract data
→ Validate facts
→ Execute tool
Never ask one prompt to be your entire company.

𝟯. 𝗙𝗿𝗼𝗺 𝟮𝟬% 𝗔𝘂𝘁𝗼𝗺𝗮𝘁𝗶𝗼𝗻 → 𝗧𝗼 𝗙𝘂𝗹𝗹 𝗟𝗼𝗼𝗽 𝗥𝗲𝗽𝗹𝗮𝗰𝗲𝗺𝗲𝗻𝘁
Automating half a task saves zero brainpower.
If you still have to verify every line, friction wins.
Pick one 15-minute repetitive task.
Automate 100% of it.
Input in. Output out. No human middleman.

━━━━━━━━━━━━━━━━━━━━━

𝗧𝗵𝗲 𝗯𝗼𝘁𝘁𝗼𝗺 𝗹𝗶𝗻𝗲:

A prompt is a toy.
A self-hosted workflow is leverage.

One wastes hours on hallucinations.
The other compounds while you sleep.

💬 Are you still babysitting chat prompts, or running automated background workflows?

Drop your thoughts below."""

# Update the draft content
req_update = urllib.request.Request(
    f"https://api.taplio.com/v1/posts/drafts/{DRAFT_ID}",
    data=json.dumps({"content": final_content}).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    },
    method="PATCH"
)

with urllib.request.urlopen(req_update) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    print("Draft updated successfully!")
    print("Draft ID:", res.get("data", {}).get("id"))
    print("Media count:", len(res.get("data", {}).get("media", [])))
    print("Media info:", res.get("data", {}).get("media"))
