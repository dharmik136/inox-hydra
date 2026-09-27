# Set up the studio from your own LinkedIn

Show the studio your own LinkedIn profile once, so it can fill in your details, import your posts and activity, and tell your posts apart from everyone else's.

A new install opens on **Setup**, first in the rail. It has four steps, and each ticks itself when the studio has actually seen the thing it asks for.

## Before you start

You need the studio running and a browser that can carry the extension. Edge and Brave work; Chrome does not. See [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

## 1. Connect the browser

Click **Open LinkedIn with the bridge**. The studio starts Edge or Brave with the extension loaded, on your LinkedIn feed. Sign in to LinkedIn there if it asks.

The step ticks when the extension reports in, which it does every minute while a LinkedIn tab is in view. The status line reads "Connected" with the extension's version. If it later reads "Last heard from ...", no LinkedIn tab is open in the bridge browser.

## 2. Show it your profile

Click **Open my profile**. The bridge browser opens your own profile.

A few seconds later a notice on the LinkedIn page reads "The studio found your profile. Confirm it's you in the studio's Setup screen." Back in the studio, Setup shows the name, headline and address it found, and why it thinks the profile is yours: either the edit controls only you see were on the page, or LinkedIn itself sent its "my profile" address there.

Click **Yes, that's me**. If it is not you, click **No**.

The studio never asks this about a stranger. A profile without one of those signs is not sent to the studio at all.

## 3. Your profile

Once you confirm, the studio reads your profile: name, headline, location, about, follower and connection counts, experience, education and skills. The status line lists what it has read so far, for example "Read: 3 roles, 2 schools, 12 skills".

The profile page does not show everything, so three buttons open the pages that do:

- **Read contact info** opens your contact panel. Your email, phone, birthday and websites are read from it.
- **Read all skills** opens your full skills list. The profile itself shows only a few.
- **Read profile again** reads it afresh, for example after you change your headline.

Anything the page did not show is left as it was, so a section that had not loaded yet does not erase what was read before. A field reading "Not read" is one the studio has not found yet.

Confirming also fills your name, headline and company in **Brand Studio**, but only where those are empty. What you typed there is never replaced.

## 4. Your history

Three imports read your activity pages:

| Import | What it reads |
| --- | --- |
| **Posts you wrote** | Your posts, their dates, and the counts LinkedIn shows on them. Reposts are skipped, because the writing is someone else's. |
| **Comments you left** | Your comments on other people's posts, and which post each was on. |
| **Posts you reacted to** | The posts you reacted to, and the reaction you used where the page says. |

Click **Import**. The bridge browser opens that activity page, and the extension scrolls it for you. A banner at the bottom of the page reads "Studio is importing your posts: N so far." with a **Stop** button.

- Keep the tab in view. The import pauses while the tab is hidden.
- It stops by itself when the list stops growing, and the banner reads "Done. N posts imported."
- **Stop** ends it early. What was read so far is kept.
- An import you asked for is picked up only within 30 minutes. After that, click **Import** again.

Your comments and reactions are kept as your own activity. They never become leads.

> [!NOTE]
> Scrolling is the one thing the studio does on LinkedIn on your behalf, and only on your own activity pages, only after you click **Import**. It reads what the page shows. The extension makes no requests to LinkedIn of its own.

## What this changes elsewhere

- **Leads** keeps only people who engaged with your own posts, and never you. See [Why is my lead list empty?](why-is-my-lead-list-empty.md)
- Everything read here stays in the database on this machine. The diagnostics bundle reports how many rows each table holds, not what is in them.

## Delete it

Under **Your profile**, click **NOT YOU, OR WANT IT GONE? DELETE EVERYTHING THE STUDIO HOLDS ABOUT YOU**. Your identity, profile, imported posts, comments, reactions and import history are deleted. The next time you open your profile, Setup asks again.

**LINKEDIN SESSION** at the bottom of Setup is separate. It shows whether a session is stored for sending posts to LinkedIn, with its own **Delete**. See [Connect your LinkedIn session](connect-your-linkedin-session.md).

## If it does not work

| What you see | What to do |
| --- | --- |
| Step 1 never ticks | Check the extension is loaded in the bridge browser, and open `http://127.0.0.1:8000` once in that browser so it has the studio's access key. Reload the extension after an update. |
| Step 2 never asks "Is this you?" | Open your profile from the bridge browser, not another one, and wait for the page to finish loading. If it still does not ask, LinkedIn may have changed its page; the studio refuses to guess. |
| A field reads "Not read" | Open the page that holds it with the buttons above. If it still does not fill, the extension did not recognise that part of the page. |
| The import stops early | The list may have stopped loading, or the tab was left. Click **Import again**; posts already read are not duplicated. |
