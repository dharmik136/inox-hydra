# Module 03: Inbound CRM & Relationship Pipeline Manual

The **Inbound CRM** transforms passive engagement (likes, comments, reposts) into a warm, high-converting 1-on-1 executive relationship pipeline. It operates completely air-gapped on local SQLite, ensuring zero prospect data or interaction histories ever leave your machine.

---

## 1. CRM Visual Architecture & Layout Overview

The CRM View (`#tab-crm`) is structured into 4 distinct functional zones:

```
+-------------------------------------------------------------------------------------------------------+
| 1. KPI SUMMARY ROW                                                                                    |
| [Active Prospects: 4]     [Outreach Sent: 1]     [Connected: 1]          [Meetings Booked: 1]         |
| Warm Engagers             In Progress            1st Degree Network      High Conversion              |
+-------------------------------------------------------------------------------------------------------+
| 2. ACTION & SEARCH TOOLBAR                                                                            |
| [Warm Engager Pipeline]   |  [🔍 Search input (Name, Company, Notes...)]  [⬇ Export CSV] [+ Add Prospect] |
+-------------------------------------------------------------------------------------------------------+
| 3. PIPELINE STATUS FILTER CHIPS                                                                       |
| [All Leads]   [🔥 New Leads]   [✉️ Outreach Sent]   [🤝 Connected]   [🎯 Meetings Booked]              |
+-------------------------------------------------------------------------------------------------------+
| 4. CLEAN DATA TABLE                                                                                   |
| Contact Name      | Title & Company                | Engagement | Status        | Notes      | Action |
| Aravind Sub...    | VP of Engineering @ CloudScale | Commented  | [New Lead v]  | "Decoup..."| [⚡DM][🗑]|
| Priya Sharma      | Head of Data @ NexaCorp        | Commented  | [Outreach v]  | "Observ..."| [⚡DM][🗑]|
| Marcus Vance      | Staff SRE @ FinTech Systems    | Liked      | [Connected v] | "Reacted"  | [⚡DM][🗑]|
| Elena Rostova     | Chief Architect @ Apex Global  | Reposted   | [Meeting v]   | "Decoup..."| [⚡DM][🗑]|
+-------------------------------------------------------------------------------------------------------+
```

---

## 2. KPI Summary Row

The top metric cards aggregate pipeline velocity at a glance:

1. **Active Prospects (`#crm-total-leads`)**:
   * Total number of unique individuals currently tracked across all stages.
   * Tracks warm engagers captured either automatically via the Chrome Extension or added manually.
2. **Outreach Sent (`#crm-outreach-count`)**:
   * Prospects who have received a tailored, 1-on-1 direct message.
3. **Connected (`#crm-connected-count`)**:
   * Prospects who have accepted your LinkedIn connection request (now 1st-degree connections).
4. **Meetings Booked (`#crm-meeting-count`)**:
   * High-value commercial, technical collaboration, or advisory discussions confirmed.

---

## 3. Detailed Column-by-Column Dictionary

The CRM table (`.clean-table`) contains 6 columns engineered for maximum context during outreach:

| Column Header | Data Field | Technical Description & Usage | Live Example |
| :--- | :--- | :--- | :--- |
| **Contact Name** | `name`, `profile_url` | Full name of the prospect. Renders as a clickable hyperlink that opens their authentic LinkedIn profile in a new tab without tracking parameters. | **Aravind Subramanian**<br/>`https://linkedin.com/in/aravind-sub` |
| **Title & Company** | `headline`, `company` | Professional designation and organization. Extracted via regex (`at X` or `@ X`) from the prospect's headline or entered manually. | **VP of Engineering**<br/>*CloudScale Technologies* |
| **Engagement** | `engagement_type` | How the prospect interacted with your content. Values: `Commented`, `Liked`, or `Reposted`. Commenters represent the highest conversion potential. | `<span class="badge">Commented</span>` |
| **Status** | `status` | Current relationship lifecycle stage. Interactive dropdown menu allowing instant 1-click status transitions. | Dropdown: `New Lead`, `Outreach Sent`, `Connected`, `Meeting Booked` |
| **Notes** | `notes` | Contextual notes or the exact verbatim comment written by the prospect on your post. Used by the AI to customize outreach. | *"Decoupling our ingest pipeline cut our MTTR by 40%."* |
| **Action** | Action Buttons | Execution triggers: **`⚡ DM`** (opens the Contextual Outreach Generator modal) and **`🗑`** (deletes the prospect record). | Button: `⚡ Generate DM`<br/>Button: `🗑` |

---

## 4. Search & Filter Mechanics

### Real-Time Search Bar (`#crm-search-input`)
* Provides instant multi-field querying across **Name**, **Company**, **Headline**, and **Notes**.
* Debounced at 250ms; updates the table dynamically without page reload.
* Querying `CloudScale` surfaces all leads affiliated with that company; querying `decoupling` surfaces all prospects who commented on that specific architectural topic.

### Pipeline Status Filter Chips (`#crm-status-chips`)
* Single-click buttons to filter the table by stage:
  * **All Leads**: Displays the entire contact database.
  * **🔥 New Leads**: Highlights fresh inbound commenters who have not yet received outreach.
  * **✉️ Outreach Sent**: Active conversations awaiting a reply.
  * **🤝 Connected**: Newly minted 1st-degree connections ready for deeper technical discussions.
  * **🎯 Meetings Booked**: Scheduled consulting, architectural reviews, or partnership calls.

---

## 5. Add Prospect Modal (`#prospect-modal`)

For manually entering leads discovered outside automated comment tracking:

* **Full Name\*** (Required): e.g. `David Lin`
* **Headline / Title**: e.g. `VP of Infrastructure at Nexus`
* **Company**: e.g. `Nexus Tech`
* **LinkedIn Profile URL**: e.g. `https://www.linkedin.com/in/davidlin`
* **Engagement Type**: Dropdown (`Commented`, `Liked`, `Reposted`)
* **Status**: Dropdown (`New Lead`, `Outreach Sent`, etc.)
* **Context Notes**: Free-text field to record specific discussion points or mutual connections.
* **Deduplication Engine**: If a lead with an identical `profile_url` or identical name/company already exists, the database updates the existing lead's notes rather than creating duplicate clutter.

---

## 6. Contextual DM Generator Modal (`#dm-modal`)

Clicking **`⚡ Generate DM`** opens the Contextual DM modal, which constructs a high-converting, personalized 1-on-1 direct message draft tailored to the prospect.

### The 3 Outreach Styles:

#### Style 1: `value_add` (`💡 Value Add` - Default Technical Peer Inquiry)
Engages the prospect as an intellectual peer by asking a thoughtful question related to their company's engineering scale:
```text
Hi Aravind,

Saw that you commented on my recent post on enterprise systems and architecture. Really appreciated your perspective! Your point about "Decoupling our ingest pipeline cut our MTTR by 40%..." really stood out.

Curious how you and CloudScale are currently navigating foundational observability and decoupling logic as you scale?

Would love to exchange notes if you're open to connecting.
```

#### Style 2: `resource_share` (`📑 Resource Share` - Blueprint / Checklist Offer)
Offers a concrete technical diagram or breakdown with zero high-pressure sales pitch:
```text
Hi Priya,

Thanks for commenting on my recent post on enterprise systems and architecture! Your point about "Observability without tracing is guesswork..." really stood out.

I recently put together a practical architecture blueprint and checklist detailing how engineering teams at organizations like NexaCorp decouple critical systems without downtime.

Would you find it helpful if I sent the diagram over? Happy to drop the link right here.
```

#### Style 3: `quick_chat` (`☕ Quick Chat` - 15-Minute Low-Key Coffee)
A low-friction invitation to swap notes over a brief virtual sync:
```text
Hi Elena,

Great seeing you in the comments on my post regarding enterprise systems and architecture!

I have been following Apex Global's trajectory and love connecting with fellow leaders navigating technical scale.

If you are ever open to a low-key 15-minute virtual coffee to swap notes on engineering architecture, I would love to connect.
```

### Strict Quality Rules:
* **Zero Em-Dash Rule**: Strictly enforces the absence of em-dashes (` - `) and double hyphens (`--`).
* **1-Click Copy**: Clicking **`📋 Copy to Clipboard`** copies the rendered script and displays a confirmation toast.

---

## 7. CSV Export Engine

Clicking **`⬇ Export CSV`** calls `/api/crm/export`:
* Emits an RFC-4180 compliant CSV stream named `linkedin_studio_crm_leads.csv`.
* Formats all columns with sanitized quoting to prevent CSV injection vulnerabilities.
* Ideal for local backup, importing into Notion databases, or syncing with enterprise CRM tools (HubSpot, Salesforce).
