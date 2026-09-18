# Deep QA Brief: Test Inox Hydra As A User, Not As A Reader

> **For**: an AI agent with a browser and a terminal
> **Target**: the released portable build, not a source checkout
> **Status**: active brief. Report findings in the format at the end.

---

## 0. The One Rule

**Reading the source code is not evidence. Only observed behaviour is.**

A previous QA pass reported "draft persistence: 100% persisted" after reading
`initEditor()` and concluding it worked. It did not work. Saving a draft and
reopening the app showed a completely different seeded post, because the restore
query asked for `status=scheduled` while a saved draft has `status=draft`. The
data was safe in SQLite the whole time, so every code path *looked* correct. The
user's experience was that their writing had vanished.

That same pass reported the Inspirations tab shows "5 templates" without noticing
the product advertises 356 in four places.

So for every claim you make in your report you must attach one of:

- a screenshot showing the state
- a DevTools network entry (method, URL, status, response body)
- a browser console error, verbatim
- a terminal command and its actual output

If you cannot produce one of those, write **"could not verify"**. That is a
perfectly acceptable finding. An unverified claim stated as fact is worse than
no claim, because it closes an issue that is still open.

You may read source code to form a hypothesis about *why* something broke. Never
to decide *whether* it broke.

---

## 1. Environment Setup

### 1.1 Get the build the way a real user would

Do not clone the repository. Download the published artifact:

```bash
# Latest release page
https://github.com/dharmik136/inox-hydra/releases/latest
# Download InoxHydra-<version>-win64.zip (about 40 MB)
```

On Windows, before extracting: right click the ZIP, Properties, tick
**Unblock**, OK. Record whether you had to do this and what happened if you
did not. First run friction is itself under test.

Extract anywhere, then run `InoxHydra.bat`. The app serves on
`http://127.0.0.1:8000`.

### 1.2 Tools to install

```bash
# Browser automation. This is the primary instrument.
pip install playwright
playwright install chromium

# Making real test files rather than empty stubs
pip install pillow reportlab

# HTTP inspection from the terminal
pip install httpx
```

A real PDF, image and video are required. Empty or truncated files are not a
valid test, because the failure being hunted may depend on real file structure.

```python
# Generate real fixtures, do not fabricate bytes
from reportlab.pdfgen import canvas
c = canvas.Canvas("deck.pdf")
for i in range(5):
    c.drawString(100, 700, f"Carousel slide {i+1}")
    c.showPage()
c.save()

from PIL import Image
Image.new("RGB", (1080, 1080), (30, 41, 59)).save("square.png")
Image.new("RGB", (4000, 3000), (12, 74, 110)).save("huge.jpg", quality=95)
```

For video, download any small real MP4. Do not hand craft one.

### 1.3 Driving the browser

Playwright must be used with the **network log and console log captured for the
entire session**. Most of the bugs you are hunting are visible only there.

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)   # watch it, do not guess
    ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                              accept_downloads=True)
    page = ctx.new_page()

    console = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
    page.on("pageerror", lambda e: console.append(f"PAGEERROR: {e}"))

    requests = []
    page.on("response", lambda r: requests.append((r.request.method, r.url, r.status)))

    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    # ... interact ...
    # At the end of EVERY journey, dump console and requests into the report.
```

Run headed at least once per journey. Some failures are visual (an element
renders off screen, a spinner never stops, a modal traps focus) and are
invisible to assertions.

---

## 2. Known Suspects

These are already suspected. Confirm or deny each with evidence. Do not assume
the list is complete, and do not stop when you have confirmed them.

### 2.1 PDF upload fails for the user

Reported: "the file is not uploading like a PDF".

**What is already established, so do not repeat it:** the HTTP API works. A
POST of a real PDF to `/api/media/upload` returns 200 with
`media_type: "carousel"`, `page_count: 1`, and the file is served back at its
`/assets/uploads/...` URL with `Content-Type: application/pdf`.

So the failure, if real, is **above the API**. Candidates to investigate in the
browser:

- the drag and drop handler versus the click-to-browse file picker. Test BOTH.
  They are often different code paths and only one is broken.
- the `accept` attribute on the file input silently filtering `.pdf` out of the
  picker, so the user cannot even select the file
- the upload firing but the UI never updating, so the user believes it failed
- the carousel preview failing to render the returned PDF, which looks
  identical to "upload failed" from the user's side
- a console error thrown after a successful 200
- file size. Try a 1 page PDF, a 15 page PDF, and one over 20 MB.
- a filename with spaces, unicode, or an uppercase `.PDF` extension

Report exactly where the chain breaks: does the network tab show the POST at
all? What status? Does the UI change? Does the console error?

### 2.2 Inspirations count is advertised as 356 and is actually 5

`/api/inspirations` returns `total_vaulted: 5`. The UI hardcodes "356" in
`index.html`. The README and `docs/modules/04_VIRAL_SWIPE_FILE.md` claim 356.

Confirm what a user actually sees on the Inspirations tab and report the number
displayed versus the number of cards rendered.

### 2.3 Draft restore was just fixed, so verify the fix

Save a draft, fully close the app (terminate the Python process and confirm port
8000 is free), reopen, and confirm **your own draft text** is what appears in the
editor. Then repeat with two drafts saved, and confirm the most recent wins.

---

## 3. Journeys To Run

Run each as an uninterrupted sequence, as a person would. Capture a screenshot
at every step where the screen changes.

### Journey A: First launch, cold

1. Fresh extract, never run before. Delete `%LOCALAPPDATA%\InoxHydra` first so
   it is genuinely a first run.
2. Launch. Time how long until the UI is usable.
3. Does anything look broken, empty, or still loading after 30 seconds?
4. Count every warning dialog, security prompt, and click required.

### Journey B: Write and keep a post

1. Type a post of about 600 characters including line breaks.
2. Watch the character counter, the mobile fold indicator, and the preview.
3. Does the "see more" fold line appear where the preview claims (~140 chars)?
4. Save it. Note the exact confirmation message.
5. Close the app completely. Reopen. Is your text there?
6. Edit it, save again, close, reopen. Is the edit there?

### Journey C: Media, the suspected break

1. Attach `square.png` by clicking the upload control.
2. Attach `square.png` by dragging it onto the dropzone.
3. Repeat both for `deck.pdf`.
4. Repeat both for the MP4.
5. Repeat for `huge.jpg` (4000x3000).
6. For each: does a preview appear? Does the post preview show it? Does it
   survive a page refresh? Does it survive an app restart?
7. Delete an attachment. Does it disappear from the UI and from disk?

### Journey D: The other tabs

For Schedule, CRM, Inspirations, Analytics, AI Command, Docs and Settings:

1. Open the tab. Does it render without console errors?
2. Is it populated or empty?
3. Click the primary action on the tab. Does it do something visible?
4. Note anything that looks like placeholder or lorem content.

### Journey E: Break it on purpose

1. Upload a file with a wrong extension (rename a `.txt` to `.pdf`).
2. Upload a 0 byte file.
3. Paste 50,000 characters into the editor.
4. Click Save rapidly ten times. Do you get ten duplicate posts?
5. Open the app in two browser tabs and edit in both. What happens?
6. Stop the backend while the UI is open. Does the UI say anything useful, or
   does it fail silently?
7. Restart the backend. Does the UI recover, or must it be reloaded?

### Journey F: The support toolkit

1. Run `InoxHydra-CLI.bat doctor`. Is the output accurate about your state?
2. Run `InoxHydra-CLI.bat doctor --bundle`. **Open the file and read it.**
   Confirm no credential appears in plain text.
3. Run `backup`, then delete a post in the UI, then `restore` the backup.
   Did your post come back?
4. Run `export --format csv`. Open the CSVs. Is your content actually in them?
5. Run `update status`. Confirm it reports checks are off by default.

---

## 4. What To Pay Attention To

- **Silent failures.** Anything that returns 200 but changes nothing on screen.
  These are the worst class, because the user has no idea it failed.
- **The gap between what the UI claims and what exists.** Counters, badges and
  labels that are hardcoded rather than read from the API.
- **State that does not survive.** Anything that is fine until you restart.
- **Error messages a non-technical person cannot act on.** "Failed to save post:
  NetworkError" is not actionable.
- **Anything that mentions a file path.** The product must never show a path
  inside the install folder for user data. It belongs in `%LOCALAPPDATA%`.

---

## 5. Reporting Format

For each finding:

```
FINDING: <one line, what a user would say happened>
SEVERITY: blocks-use | data-loss | misleading | cosmetic
JOURNEY: <which journey, which step>
EXPECTED: <what a reasonable user would expect>
ACTUAL: <what happened>
EVIDENCE:
  - screenshot: <filename>
  - network: POST /api/media/upload -> 200, body: {...}
  - console: TypeError: Cannot read properties of null ...
REPRODUCIBLE: <yes, N of N attempts | intermittent, N of N>
```

Then a summary table, and finally:

- **What I could not verify, and why.** Be explicit. This section is mandatory
  and an empty one will be treated as an incomplete report.
- **What I did not test.** Also mandatory.

Do not rank findings by how interesting they are. Rank by what stops a person
from using the product.

---

## 6. Explicitly Out Of Scope

- The Chrome extension. It is not in the Web Store, so it cannot be installed
  the way a user would, and Chrome disables unpacked extensions after browser
  updates. Do not test it and do not report on it.
- Connecting a real LinkedIn account. Use only seeded and locally created data.
- Code style, architecture opinions, and refactoring suggestions. Not wanted
  here. This brief is about observed behaviour only.
