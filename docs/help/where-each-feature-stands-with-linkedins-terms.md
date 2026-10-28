# Where each feature stands with LinkedIn's terms

Read LinkedIn's own words on third-party software, and where each thing the studio and the extension do stands beside them, so you decide with the text in front of you.

Your LinkedIn account is yours, and it is the account that answers for anything a tool does with it. This page quotes the two documents LinkedIn applies, exactly as they read on the dates given, and then says, feature by feature, which words each one touches. None of it is legal advice: it is the studio's own reading, written so that you can make yours.

## What LinkedIn says

**The User Agreement, section 8.2 ("You agree that you will not"), effective on November 3, 2025, as read on 26 October 2026**, at linkedin.com/legal/user-agreement. Six of its nineteen items concern tools like this one, each named here by its position in LinkedIn's list:

- **Item 1:** "Create a false identity on LinkedIn, misrepresent your identity, create a Member profile for anyone other than yourself (a real person), or use or attempt to use another's account (such as sharing log-in credentials or copying cookies);"
- **Item 2:** "Develop, support or use software, devices, scripts, robots or any other means or processes (such as crawlers, browser plugins and add-ons or any other technology) to scrape or copy the Services, including profiles and other data from the Services;"
- **Item 4:** "Copy, use, display or distribute any information (including content) obtained from the Services, whether directly or through third parties (such as search tools or data aggregators or brokers), without the consent of the content owner (such as LinkedIn for content it owns);"
- **Item 9:** "Reverse engineer, decompile, disassemble, decipher or otherwise attempt to derive the source code for the Services or any related technology that is not open source;"
- **Item 13:** "Use bots or other unauthorized automated methods to access the Services, add or download contacts, send or redirect messages, create, comment on, like, share, or re-share posts, or otherwise drive inauthentic engagement;"
- **Item 15:** "Overlay or otherwise modify the Services or their appearance (such as by inserting elements into the Services or removing, covering, or obscuring an advertisement included on the Services);"

**The Help Center article "Prohibited software and extensions" (answer a1341387), marked "Last updated: 2 years ago" when read on 26 October 2026:**

> "In order to protect our members' data and our website, we don't permit the use of any third party software, including "crawlers", bots, browser plug-ins, or browser extensions that scrape, modify the appearance of, or automate activity on LinkedIn's website."

> "Any member who uses tools for such purposes is in violation of the User Agreement. This means that they risk having their accounts restricted or shut down. They also risk the possibility that any prohibited tools they're using may become non-operational without notice."

**The Help Center article "Automated activity on LinkedIn" (answer 90586), marked "Last updated: 3 weeks ago" when read on 26 October 2026:**

> "we don't allow the use of third-party software or browser extensions that scrape, modify the appearance of, or automate activity on LinkedIn's website."

The three words that matter are the Help Center's: a tool that would **scrape**, **modify the appearance of**, or **automate activity on** LinkedIn's website. By that text there is no carve-out for a tool that reads only your own pages. What differs between tools is which of those words each one touches, how lightly, and what has been enforced. The studio's reading of its own features follows.

## Where each feature stands

| Feature | On by default? | Which words it touches | The studio's reading |
| --- | --- | --- | --- |
| Reading your own pages in the bridge browser (your profile, your posts, your analytics, the people who engaged on your posts) | Yes, once you pair the extension | Item 2, "copy". Item 4 for other people's comments. | Tolerated in practice, not permitted in text. The extension copies what is on a page you opened yourself, with you present, into a database on your own disk, and nothing goes to a server of ours. Every surviving creator extension does the same, and no enforcement against reading your own pages in the foreground has been documented; the tools that were stopped reused the login cookie on a vendor's servers or drew over LinkedIn's pages at scale. Tolerance can end "without notice". |
| The history import (the extension clicks LinkedIn's "Show more results" and scrolls your own activity pages, only after you press Import) | No, only when you press Import | Item 13, "automated methods to access the Services", for the clicking; item 2 for the copying | Tolerated in practice, not permitted in text. It runs on your own pages, on a press, at a human pace, pausing while the tab is hidden, with Stop on the page. |
| The `data-urn` mark on feed cards: a small script that runs inside LinkedIn's own page code reads each post card's id, which LinkedIn keeps only in its page code, and writes it onto the card as an invisible `data-urn` attribute, so the extension knows which post a comment or reaction belongs to | Yes, on every LinkedIn page, from installation | Item 15, "modify the Services", lightly; and, arguably, item 9, because it reads LinkedIn's page code to find the id. | Tolerated in practice, not permitted in text. It is the one mark the extension makes in LinkedIn's page: an attribute nobody sees, which covers nothing and sends nothing anywhere. |
| The import banner with Stop | No, only while a history import you started is running | Item 15, "inserting elements". | Tolerated in practice, not permitted in text. It carries the Stop control you need on the page being scrolled, and is never placed near an advertisement. Apart from it and the `data-urn` mark, nothing of the studio's is put into LinkedIn's page: what the extension read is confirmed on its badge and in its side panel, outside the page. |
| Reading LinkedIn's network responses ("Read LinkedIn's network responses" in the popup) | No. Off when installed; a switch you turn on | Item 2, more literally; "modify the appearance of" in the Help Center's sense, because page code is altered. | Opt-in, and disclosed beside the switch, which says it works "by wrapping the page's fetch function, which LinkedIn may treat as automation". It copies responses LinkedIn's own page already downloaded and makes no request of its own. The sanctioned way to exact figures is LinkedIn's own analytics export, which the studio imports from Setup; see [Import LinkedIn's analytics export](import-linkedins-analytics-export.md). |
| Placing a draft in LinkedIn's composer ("Insert into LinkedIn Composer") | No, only when you press Insert | Item 13, lightly: a scripted click opens the composer and the text is typed; no post is created. | Tolerated in practice, not permitted in text. Nothing acts on LinkedIn except when you press Insert, and Post stays yours to press. |
| Send to LinkedIn (hands a finished post to LinkedIn's own scheduler through its private API, with your own session) | No. Refused until the studio is started with `INOX_ALLOW_LINKEDIN_EGRESS=1`, and acknowledged once per profile | Item 13, "create ... posts" by "unauthorized automated methods", squarely; the Help Center's "automate activity". | The studio's clearest match to the text, and the privacy policy says it writes outside LinkedIn's published terms. Off by default, a single write on a press, and available in your first creator profile only: a second profile cannot sync a session or send, because item 1 bars "copying cookies" to use another's account and the studio cannot tell whose browser a session came from. An official posting route through LinkedIn's own API is what would replace it. |
| Syncing your LinkedIn session into the studio | No, only when you press Sync LinkedIn Session | None by itself. Item 1 only if the account is not yours. | Your own cookie, on your own machine, for the one feature above. First profile only, for the reason just given. |
| The data archive import and the analytics export import | Setup leads with the archive | Touches none of the words quoted here. Both are downloads LinkedIn makes for you. | Outside the words quoted here: LinkedIn's own export features, which you request and hand to the studio. The text does not settle whether LinkedIn counts the figures it computes as content it owns under item 4, and the connections in your archive are other members' information. |

What is not here, because the studio does not do it: it never comments, reacts, connects, follows or messages for you, never reads anyone's pages but the ones you open, never acts on LinkedIn in the background, and never sends your data to a server of ours. In the background the extension only notices when you sign in to or out of LinkedIn, so it stops filing readings under the wrong account, retries sending held captures to the studio on this computer, checks in with that studio once a minute, and looks at its own folder every five minutes to notice an update. When it is installed or updated, it starts its readers in the LinkedIn tabs you already have open, as reloading each tab would; they read and click nothing more than on a page you open. See [What leaves this machine, and when](what-leaves-this-machine.md).

## What "tolerated, not permitted" means for you

- The text leaves no room for a reading extension; the enforcement record so far has not reached a tool that reads only the member's own pages in the foreground. Both are facts, and they pull in different directions. The studio's default install stays on the lighter side of every line the stopped tools crossed, and it says so plainly rather than claiming a permission it does not have.
- The two features that sit closest to the text, network reading and Send to LinkedIn, are off until you turn them on, and the words above are what you are agreeing to when you do.
- If LinkedIn restricts an account for "automated activity", its own notice says to review and disable the software or extension; the studio's switches are in the extension's popup and in the environment the studio starts from, and nothing keeps running without them.
- The three documents quoted here change. The dates above are when they were read; check the pages themselves before relying on a quote.

## Where the words come from

- LinkedIn User Agreement: linkedin.com/legal/user-agreement (section 8.2), effective 3 November 2025.
- LinkedIn Help, "Prohibited software and extensions": linkedin.com/help/linkedin/answer/a1341387.
- LinkedIn Help, "Automated activity on LinkedIn": linkedin.com/help/linkedin/answer/90586.
- The studio's own account of what it reads and sends: the privacy policy in Docs, and [What leaves this machine, and when](what-leaves-this-machine.md).
