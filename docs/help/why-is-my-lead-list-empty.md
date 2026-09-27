# Why is my lead list empty?

Work through the chain a lead travels, from a LinkedIn page to the Leads surface, and find where it stopped.

A fresh install has no leads. The studio never fetches people from LinkedIn on its own: the Leads surface says "No leads captured yet" until the browser extension has seen someone engage with one of your own posts, on a page you opened yourself. (Four invented sample leads appear only if the studio was started with `INOX_DEMO_DATA` set while the lead list was still empty.)

## How a lead gets in

Every link in this chain has to hold:

1. **The extension is loaded in Edge or Brave.** On the empty Leads surface, the buttons under **OPEN LINKEDIN WITH THE BRIDGE** start whichever of those browsers is installed, with the extension attached, on your LinkedIn feed. See [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).
2. **You opened the studio once in that same browser.** Go to `http://127.0.0.1:8000` in that browser. When the studio page loads, it gives that browser a local access token, and the extension reads the token from there. Each browser keeps its own copy of the token, so opening the studio in a different browser does not help this one.
3. **You confirmed your profile in Setup.** A lead is someone who engaged with your post, and the studio can only tell your posts from other people's once it knows who you are. Until then nothing is kept. See [Set up the studio from your own LinkedIn](set-up-the-studio-from-your-linkedin.md).
4. **You open a LinkedIn page that shows engagement on your post.** That means a page under `/feed/` (your feed, or a single post opened from it) or a post page under `/posts/`. Commenters are read from the comments that are open on the page. People who reacted are read only when the reactions list itself is open.
5. **A small "LinkedIn Studio" notice appears on the LinkedIn page.** It says how many engagers on your post were captured.
6. **You reopen Leads.** The list is read when you open the surface and after you change a lead's status. It does not refresh while you are looking at it.

## What you see, and what to do

| What you see | Why | What to do |
|---|---|---|
| No notice at all on LinkedIn | The post is not yours, the extension is not running in this browser, the page is not one it reads, or no comments or reactions list is open. It stays quiet about other people's posts on purpose, and about people it has already sent from this tab. | Check that you are in Edge or Brave with the extension loaded, open the comments or the reactions list on a post, and wait a few seconds. The extension checks at most once every 4 seconds as the page changes. |
| "LinkedIn Studio: could not reach your studio, so nothing was saved." | The studio is not running, or this browser has no studio token, so the studio refused the request. | Start the studio, open `http://127.0.0.1:8000` once in this browser, then **reload the LinkedIn tab**. Without a reload, the tab does not resend people it already tried. |
| "LinkedIn Studio: confirm your profile in the studio's Setup screen to start capturing leads from your posts." | The studio does not yet know which posts are yours, so it kept nobody. Shown once per page. | Open **Setup** in the studio and confirm your profile. |
| "LinkedIn Studio: N engager(s) had no profile link and were not saved." | A person with no profile link cannot be told apart from anyone else with the same name, so they are skipped on purpose. | Nothing to fix. Other people on the same post are still saved. |
| A "captured" notice appeared, but Leads is still empty | Leads was already open and has not reread the list. | Switch to another surface and back to Leads. |
| LEAD PIPELINE UNAVAILABLE | The interface could not read the lead list from the studio. | See [The studio will not open or shows an error](the-studio-will-not-open.md). |

> [!NOTE]
> If Chrome is installed, the empty Leads surface names it but offers no button for it, because Chrome ignores the flag that loads the extension. The surface says so ("IGNORES THE EXTENSION FLAG, SO THE BRIDGE WOULD NOT ATTACH"). The studio also suggests loading the extension by hand, but it does not check whether that works in Chrome. Use Edge or Brave.

## Pages that never produce leads

- **Profile pages** (any address under `/in/`). This is deliberate. A profile page shows that person's comments on other people's posts, and recording those would credit your content with engagement it never got. Your own profile and activity pages are read, but for **Setup**, never as leads.
- **Messaging, notifications, search and job pages.** The extension does not look for engagers on these pages at all, so a pop-up there never becomes a lead, even if it shows names and profile links. On the feed and post pages, a pop-up counts only if it is a reactions list.

On the feed, the extension reads commenters and reactions on any post you have open, but the studio keeps only those on posts written by you, or on posts it has already imported as yours. You are never recorded as your own lead. Leads captured before this rule existed are not removed automatically.

## Check the extension popup

Click the extension's toolbar icon. The popup asks the studio through the extension, the same way a capture does, so what it shows is what a capture would meet:

| Server line | Meaning |
| --- | --- |
| Online | The studio answered this browser. The badge beside it reads "Ready", or "Finish Setup in the studio" if you have not confirmed your profile. |
| Not paired | The studio is running but refuses this browser. Open `http://127.0.0.1:8000` in it once. |
| Offline | The studio is not running. |

Its **Sync LinkedIn Session** button copies your session only; it has nothing to do with capturing leads. See [Connect your LinkedIn session](connect-your-linkedin-session.md).

## Analytics empty too?

Analytics uses the same extension and the same token, so if both are empty, fix the token first, as described above. Then see [Read your analytics](read-your-analytics.md).
