# Review your leads and draft a message

Read each captured person's dossier, set their pipeline stage, and draft a message you send yourself.

Leads are people the browser extension saw commenting on or reacting to posts. Each person is one lead, matched only by the `/in/` part of their profile link, never by name. If the list is empty, see [Why is my lead list empty?](why-is-my-lead-list-empty.md).

## The lead stream

Open **Leads** in the rail. The left column, **Lead stream**, shows how many people you have and a **CSV** download link. Each row shows:

- the person's name and LinkedIn headline
- how they engaged, such as COMMENTED or LIKED (ENGAGED when unknown)
- their pipeline stage

The first lead opens automatically. Click any row to open that person. The list loads when you open **Leads**, so leave and reopen it to see people captured since.

To narrow the stream, type in **Find a lead** (a name, company, headline or words from your notes; accents do not matter, so "zoe" finds Zoë), or choose a stage in the **Stage** list. The count then reads, for example, "3 OF 120". The stream shows 200 people at a time; click **Show more** at the bottom for the next 200. To search what people said in their comments too, press **Ctrl+K**; see [Search everything with Ctrl+K](use-the-command-palette.md).

On a phone-sized window the stream and the dossier take turns: click a person to open their dossier, and **Back to the lead stream** to return.

## The dossier

The right side is a sheet on one person. Under their name, **OPEN THEIR PROFILE ON LINKEDIN** opens their LinkedIn profile in your browser, so you can look at the right person before messaging them. It appears only when the studio holds a LinkedIn profile address for them.

| Field | What it shows |
| --- | --- |
| Company | Taken from the headline, for example the part after "at". Left blank if the headline names none. |
| Seniority | A level worked out from the headline, or Unknown |
| ICP score | 0 to 100 and its tier: VIP from 80, Qualified from 60, Nurture from 30, otherwise Disqualified. A student or intern often scores 0, which is a score. "Not scored" appears only for someone added by hand, with nothing captured. |
| First seen | The first time the bridge read an engagement of theirs. For someone added by hand and never seen by the bridge, **Added** and the date they were added instead |
| Last seen | The last time the bridge read an engagement of theirs |
| Times seen | How many times the bridge read their engagements, the same comment read again included |

Once you have imported your LinkedIn archive, a line under these says "Connected since" and the date when the person is one of your connections, as of the day the archive was imported; otherwise it says they are not among your connections, or that it cannot tell, because the bridge read their profile link as a member number. See [See who keeps coming back](see-who-keeps-coming-back.md).

The ICP score is calculated on this machine by fixed rules: seniority words in the headline, how they engaged and how long their comment was, whether a company is known and what it is called, and whether the comment contains a question mark. It is worked out again at every capture, from their current headline and their best recorded engagement, so it can fall as well as rise.

**Recent interactions** lists up to 8 engagements with any comment text. Each comment appears once, however often you reopened the post, with the time it was first recorded. Times and dates on the dossier are in this computer's time zone, as on **Today**. A reaction carries no text. Under each one, the studio says where it happened:

- **ON YOUR POST**, followed by the opening of that post when the studio has it.
- **ON SOMEONE ELSE'S POST, CAPTURED BEFORE THE STUDIO KNEW WHICH POSTS WERE YOURS**, in orange, for an engagement recorded before you set up the studio. See the next section.
- Nothing, when the studio cannot tell.

**Notes** holds your own notes on the person, or NO NOTES YET. Click **EDIT NOTES**, write up to 2,000 characters, and click **Save notes**; **CANCEL** leaves them as they were. Saving notes does not change the person's stage.

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

Under the stages, each change is listed with its date, for example "OCT 21: NEW LEAD TO CONNECTED". When you opened the person from one of your posts, in **Replies** under the post their comment is on or from **Who engaged** in a post's detail on **Posts**, the dossier says "OPENED FROM YOUR POST" with the post's opening, and a change you make there is listed with that post, for example "OCT 21: NEW LEAD TO CONNECTED, FROM YOUR POST "Freight is a data problem..."". That is how the studio answers which posts brought the people you went on to talk to. A change made after opening the person from the stream, or made before this version, names no post. The studio refuses to record a change as coming from a post the person never engaged with.

## Forget a person

If someone asks you to delete what you hold about them, or the studio captured the wrong person, open their dossier and click **Forget this person** at the bottom. The button turns orange and names them, for example **Forget Asha Rao, it cannot be undone**. Click it again to forget them, or **CANCEL**. The studio removes the person, everything they said, their stage history and your notes on them, and the top of the stream says so. Exports you made earlier still hold them; export to Obsidian again to remove their note from the vault. Older backups also still hold them until rotation removes those backups; to remove them from backups too, open **Settings**, **Storage and privacy**. Deleting the leads that engaged only with other people's posts says the same before you confirm.

## Draft a message

1. In **THE POST THEY ENGAGED WITH**, you can type the subject of the post. The box is optional. When the dossier shows which of your posts they engaged with (**ON YOUR POST**), the box names that post, and left blank the draft quotes the post's first sentence. **Reply to their comment** uses only the post their comment was on; the other styles use that post, or else the latest of yours they reacted to. When the studio does not hold the post, the openers say only "my recent post", and the box says it is needed for **Reply to their comment**, which never names a different post.
2. To offer them something, type what it is in **WHAT YOU WOULD SHARE WITH THEM**, for example "the checklist I use for orders".
3. Click a style: **Peer question**, **Suggest a call**, **Offer something** or **Reply to their comment**.
4. Read the draft. Its label says which control wrote it.
5. Click **COPY**, then edit and send it yourself in LinkedIn.

| Control | What it writes |
| --- | --- |
| Peer question | Names their engagement, then asks how it looks from where they sit, naming their company when the studio knows it |
| Suggest a call | Suggests a short call to swap notes |
| Offer something | Offers exactly what you typed in the share box, and nothing else. Greyed out until you type something. |
| Reply to their comment | Quotes up to the first 60 characters of their latest comment |

The drafts use only the person's record (first name, company, how they engaged, their comment) and what you type in the two boxes. They say nothing about your work, your company or your background, because the studio does not know it. If a comment contains a question, **Reply to their comment** says it saw their question instead of thanking them for the comment. Read every draft before sending it.

If the topic box is empty and the studio does not hold the post they engaged with, the openers name no subject: **Peer question** and **Offer something** say only "my recent post", and **Suggest a call** says only "my post". **Reply to their comment** writes nothing until you fill in the box whenever the studio does not hold the post their comment was on, even if it holds another post they reacted to.

## What happens

Each draft is a fill-in template built from the stored record: first name, company, how they engaged, their comment, your topic and what you would share. No AI provider is used, even with a key configured, and nothing leaves this machine. Nothing is sent from the studio. As the panel says, LinkedIn messages are not something the studio can send for you.

## Export your leads

Click **CSV** above the stream to download every lead as `linkedin_studio_crm_leads.csv`. Its Qualification Tier column uses the studio's one tier rule: TIER_1_VIP from an ICP score of 80, QUALIFIED from 60, NURTURE from 30, otherwise DISQUALIFIED. Its Status column shows the stage as the dossier does, such as Outreach Sent. Names, headlines and notes are written by other people, so any cell that starts with =, +, -, @ or a tab begins with an apostrophe: a spreadsheet then shows it as text instead of running it as a formula.

## If it does not work

| You see | What it means |
| --- | --- |
| LEAD PIPELINE UNAVAILABLE | The lead list could not be loaded. Check the studio is running and reload. |
| DOSSIER UNAVAILABLE | That person's record could not be loaded. |
| **Reply to their comment** is greyed out | Hover it: "This lead has left no comment to reply to". Use one of the other three. |
| **Offer something** is greyed out | Hover it: "Say what you would share with them, above". Type it in the share box. |
| "Say which post they commented on, above, and a reply can be drafted." | The studio does not hold the post they commented on, so **Reply to their comment** needs the topic box. Type the subject of the post and press it again. |
| "Lead not found" | The lead no longer exists. Reopen **Leads**. |
| "The removal was refused." or another message under **Remove these** | The deletion did not run. Nothing was removed. Reopen **Leads** and try again. |
