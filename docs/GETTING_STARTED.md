# Getting Started with LinkedIn Studio Enterprise

This guide will walk you through launching, configuring, and operating **LinkedIn Studio Enterprise** on your Windows workstation.

---

## 📋 Prerequisites

Before running LinkedIn Studio, ensure your environment meets the following requirements:
* **Operating System**: Windows 10/11 (64-bit)
* **Python Runtime**: Python 3.10+ (Python 3.13 recommended)
* **Web Browser**: Google Chrome (for the Extension and borderless App Mode)
* **Dependencies**: `fastapi`, `uvicorn`, `pydantic`, `pillow`, `requests` (all pre-installed in your environment)

---

## 🚀 Step 1: Launching the Studio

### Option A: 1-Click Native Desktop Mode (Recommended)
Double-click [`launch_studio.bat`](../launch_studio.bat) in the project root or the **LinkedIn Studio** desktop shortcut.

**What Happens Under the Hood:**
1. A PowerShell check verifies if port 8000 is accepting connections.
2. If inactive, the script spawns `python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000` in a minimized background console.
3. It detects your Google Chrome installation and starts it with `--app="http://127.0.0.1:8000" --window-size=1440,920`.
4. The studio opens as a dedicated desktop application with its own Windows taskbar icon, without browser tabs or an address bar.

### Option B: Command Line (Developers)
```powershell
# Navigate to wherever you installed or cloned Inox Hydra
cd "C:\path\to\inox-hydra"

# Start the local FastAPI server
python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000

# Open in your browser of choice
start http://127.0.0.1:8000
```

---

## 🧩 Step 2: Loading the Chrome Extension Bridge

The Chrome Extension connects your logged-in LinkedIn session to the local studio safely and passively.

1. Open Google Chrome and visit `chrome://extensions`.
2. Enable **Developer mode** using the toggle in the top-right corner.
3. Click **Load unpacked**.
4. Select the `studio\extension` folder inside your Inox Hydra install directory.
5. You will see **LinkedIn Studio Bridge** loaded, showing the current version.

### What the Extension Does:
* **Background Token Sync**: Reads your `li_at` and `JSESSIONID` session cookies from `linkedin.com` and synchronizes them to `http://127.0.0.1:8000/api/auth/cookies`.
* **Zero-Detection CRM Capture**: Uses a passive DOM `MutationObserver` on LinkedIn comment threads to extract engager names, headlines, and profile URLs directly into your local CRM database.
* **Sidepanel Composer**: Open the Chrome sidepanel on LinkedIn to draft posts and insert hooks without leaving the feed.

---

## 🤖 Step 3: Configuring the AI Engine (Optional)

The studio operates completely offline using the **Antigravity Deterministic Local Engine**. If you wish to enable Google's cutting-edge **Gemini 2.5 Flash** cloud model:

1. In the Studio UI, click on the **AI Command Center** tab in the sidebar.
2. Under **Gemini API Engine**, paste your Google Gemini API key (`AIzaSy...`).
3. Click **Save Key**.
4. The key is written directly to the `settings` table in your local SQLite database (`linkedin_studio.db`). It is never sent to any third party.
5. The topbar status chip will update to **Gemini 2.5 Flash Live**.

---

## 🔍 Step 4: Verifying the System

To verify that all backend modules, databases, and formatting tools are functioning:

```powershell
python studio/backend/test_studio_backend.py
```

Expected Output:
```text
Running LinkedIn Studio Enterprise Tests...
Database initialized at: studio/data/linkedin_studio.db
✅ test_database_and_seed passed!
✅ test_formatters_and_rehooker passed!
✅ test_carousel_pdf passed!
✅ test_leads_crm passed!
✅ test_multi_range_kpis_and_slots passed!
✅ test_ai_engine passed (strict zero em-dash verified)!

🎉 ALL 6 ENTERPRISE TEST SUITES PASSED SUCCESSFULLY!
```

---

## 🛠 Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **Port 8000 already in use** | A previous instance of `uvicorn` is running | Run `Get-Process python \| Stop-Process -Force` in PowerShell, then re-launch. |
| **Extension shows disconnected** | Local backend server is not running | Run `launch_studio.bat` or verify `http://127.0.0.1:8000` is accessible. |
| **Lead commenters not appearing** | LinkedIn comment section not scrolled into view | Open comments on any post; the extension detects cards when visible in the DOM. |
| **Carousel PDF fonts look default** | Local system fonts fallback | Pillow falls back gracefully to `arial.ttf` or default bitmap font if custom OTF is absent. |
