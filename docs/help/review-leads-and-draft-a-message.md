# Review your leads and draft a message

Read each captured person's dossier, set their pipeline stage, and draft a message you send yourself.

Leads are people the browser extension saw commenting on or reacting to posts. Each person is one lead, matched only by the `/in/` part of their profile link, never by name. If the list is empty, see [Why is my lead list empty?](why-is-my-lead-list-empty.md).

## The lead stream

Open **Leads** in the rail. The left column, **Lead stream**, shows how many people you have and a **CSV** download link. Each row shows:

- the person's name and LinkedIn headline
- how they engaged, such as COMMENTED or LIKED (ENGAGED when unknown)
- their pipeline stage

The first lead opens automatically. Click any row to open that person. The list loads when you open **Leads**, so leave and reopen it to see people captured since. The stream has no filter of its own. To find one person, press **Ctrl+K** and type their name, their company or something they said; see [Search everything with Ctrl+K](use-the-command-palette.md).

## The dossier

The right side is a sheet on one person. Under their name, **OPEN THEIR PROFILE ON LINKEDIN** opens their LinkedIn profile in your browser, so you can look at the right person before messaging them. It appears only when the studio holds a LinkedIn profile address for them.

| Field | What it shows |
| --- | --- |
| Company | Taken from the headline, for example the part after "at". Left blank if the headline names none. |
| Seniority | A level worked out from the headline, or Unknown |
| ICP score | 0 to 100, or "Not scored" |
| First seen | The date the studio recorded them |

The ICP score is calculated on this machine by fixed rules: seniority words in the headline, how they engaged and how long their comment was, whether a company is known and what it is called, and whether the comment contains a question mark. It is worked out again at every capture, from their current headline and their best recorded engagement, so it can fall as well as rise.

**Recent interactions** lists up to 8 engagements with any comment text. Each comment appears once, however often you reopened the post, with the time it was first recorded. A reaction carries no text. Under each one, the studio says where it happened:

- **ON YOUR POST**, followed by the opening of that post when the studio has it.
- **ON SOMEONE ELSE'S POST, CAPTURED BEFORE THE STUDIO KNEW WHICH POSTS WERE YOURS**, in orange, for an engagement recorded before you set up the studio. See the next section.
- Nothing, when the studio cannot tell. **Notes** appears when the record has notes. Notes cannot be edited here.

## Remove leads from other people's posts

Before you confirmed your profile in **Setup**, the extension kept anyone who engaged with any post on your feed. Those people are other creators' audiences, and a message thanking them for commenting on your post would be wrong. The studio can find them, but only once it has your whole post history, because until then a post it does not recognise may simply be an older post of yours.

- **Your post history is not fully imported yet.** If any leads are undecided, the top of the lead stream reads "IMPORT YOUR POSTS IN SETUP AND THE STUDIO CAN TELL WHICH OF THESE LEADS CAME FROM YOUR POSTS." Nothing is offered for removal. Run **Posts you wrote** in [Setup](set-up-the-studio-from-your-linkedin.md) until it finishes.
- **Your post history is imported.** If some leads engaged only with other people's posts, the top of the lead stream reads, for example, "3 LEADS ENGAGED ONLY WITH OTHER PEOPLE'S POSTS. REVIEW".

1. Click it to see their names. Click again (it now ends **HIDE**) to close the list.
2. Click **Remove these 3**. The button turns orange and reads **Delete these 3, it cannot be undone**.
3. Click it again to delete them, or **CANCEL** to keep them.

A lead counts as someone else's only when every engagement the studio recorded names a post and none of those posts is yours. A lead with any engagement on your posts is always kept, and so is anyone you added yourself. The check runs again at the moment you delete, so someone who has engaged with your post since you opened the list is kept, and the message says so: "REMOVED 2. KEPT 1 THAT HAVE SINCE ENGAGED WITH YOUR POSTS." Deleting removes the lead and their recorded engagements from this machine. Take a [backup](back-up-restore-and-export.md) first if you might want them back.

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
> The drafts contain fixed wording about architecture and engineering. If a comment contains a question, **Reply to their comment** says it saw their question instead of thanking them for the comment. Rewrite anything that is not true of you before sending.

If the topic box is empty, the first three name no subject: **Peer question** and **Offer a blueprint** say only "my recent post", and **Suggest a call** says only "my post". **Reply to their comment** writes nothing until you fill in the box.

## What happens

Each draft is a fill-in template built from the stored record: first name, company, how they engaged, their comment and your topic. No AI provider is used, even with a key configured, and nothing leaves this machine. Nothing is sent from the studio. As the panel says, LinkedIn messages are not something the studio can send for you.

## Export your leads

Click **CSV** above the stream to download every lead as `linkedin_studio_crm_leads.csv`. Its Qualification Tier column uses the studio's one tier rule: TIER_1_VIP from an ICP score of 80, QUALIFIED from 60, NURTURE from 30, otherwise DISQUALIFIED.

## If it does not work

| You see | What it means |
| --- | --- |
| LEAD PIPELINE UNAVAILABLE | The lead list could not be loaded. Check the studio is running and reload. |
| DOSSIER UNAVAILABLE | That person's record could not be loaded. |
| **Reply to their comment** is greyed out | Hover it: "This lead has left no comment to reply to". Use one of the other three. |
| "Say which post they commented on, above, and a reply can be drafted." | **Reply to their comment** needs the topic box. Type the subject of the post and press it again. |
| "Lead not found" | The lead no longer exists. Reopen **Leads**. |
| "The removal was refused." or another message under **Remove these** | The deletion did not run. Nothing was removed. Reopen **Leads** and try again. |
