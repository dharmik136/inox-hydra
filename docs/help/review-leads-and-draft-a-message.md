# Review your leads and draft a message

Read each captured person's dossier, set their pipeline stage, and draft a message you send yourself.

Leads are people the browser extension saw commenting on or reacting to posts. If the list is empty, see [Why is my lead list empty?](why-is-my-lead-list-empty.md).

## The lead stream

Open **Leads** in the rail. The left column, **Lead stream**, shows how many people you have and a **CSV** download link. Each row shows:

- the person's name and LinkedIn headline
- how they engaged, such as COMMENTED or LIKED (ENGAGED when unknown)
- their pipeline stage

The first lead opens automatically. Click any row to open that person. The list loads when you open **Leads**, so leave and reopen it to see people captured since. There is no search, filter or delete.

## The dossier

The right side is a sheet on one person:

| Field | What it shows |
| --- | --- |
| Company | Taken from the headline, for example the part after "at". Left blank if the headline names none. |
| Seniority | A level worked out from the headline, or Unknown |
| ICP score | 0 to 100, or "Not scored" |
| First seen | The date the studio recorded them |

The ICP score is calculated on this machine by fixed rules: seniority words in the headline, how they engaged and how long their comment was, whether a company is known and what it is called, and whether the comment contains a question mark.

**Recent interactions** lists up to 8 engagements with any comment text. **Notes** appears when the record has notes. Notes cannot be edited here.

## Move a lead through the pipeline

Under **Pipeline**, click one of the four stages: **New Lead**, **Outreach Sent**, **Connected** or **Meeting Booked**. The stage updates in the dossier and in the stream. No other stages can be chosen.

## Draft a message

1. In **THE POST THEY ENGAGED WITH**, you can type the subject of the post. The box is optional. Left blank, the draft says only "my recent post". The studio does not know which post it was.
2. Click a style: **Peer question**, **Offer a blueprint**, **Suggest a call** or **Reply to their comment**.
3. Read the draft. Its label says which control wrote it.
4. Click **COPY**, then edit and send it yourself in LinkedIn.

| Control | What it writes |
| --- | --- |
| Peer question | Names their engagement, then asks how they and their company handle "foundational observability and decoupling logic" |
| Offer a blueprint | Offers "a practical architecture blueprint and checklist" |
| Suggest a call | Suggests a 15-minute virtual coffee |
| Reply to their comment | Quotes up to the first 60 characters of their latest comment |

> [!IMPORTANT]
> The drafts contain fixed wording about architecture and engineering. If a comment contains a question, **Reply to their comment** also adds "We found decoupling background ingestion eliminates write lock contention entirely." Rewrite anything that is not true of you before sending.

If the topic box is empty, the first three name no subject: **Peer question** and **Offer a blueprint** say only "my recent post", and **Suggest a call** says only "my post". **Reply to their comment** still uses "sovereign creator stack".

## What happens

Each draft is a fill-in template built from the stored record: first name, company, how they engaged, their comment and your topic. No AI provider is used, even with a key configured, and nothing leaves this machine. Nothing is sent from the studio. As the panel says, LinkedIn messages are not something the studio can send for you.

## Export your leads

Click **CSV** above the stream to download every lead as `linkedin_studio_crm_leads.csv`.

## If it does not work

| You see | What it means |
| --- | --- |
| LEAD PIPELINE UNAVAILABLE | The lead list could not be loaded. Check the studio is running and reload. |
| DOSSIER UNAVAILABLE | That person's record could not be loaded. |
| **Reply to their comment** is greyed out | Hover it: "This lead has left no comment to reply to". Use one of the other three. |
| "the server returned no draft" | The stored comment is a capture placeholder, such as "Reacted to post on LinkedIn", not something they wrote. This is usual for people who reacted. |
| "Lead not found" | The lead no longer exists. Reopen **Leads**. |
