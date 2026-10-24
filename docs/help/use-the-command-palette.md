# Search everything with Ctrl+K

Find a post, a lead, a hook form or a help article from any surface, and open it where it lives.

## Open search

- Click the magnifier at the top of the rail, above the surfaces. Its name is **Search everything (Ctrl+K)**.
- On every surface except the Composer, you can also click **Search everything** at the right of the header.
- Or press **Ctrl+K** (**Cmd+K** on a Mac). It works from every surface, including while you are typing in the editor.

To close it, press **Escape**, press **Ctrl+K** again, or click the dimmed area around the box.

## Find something

1. Type in the box. Every word you type has to appear somewhere in an item for it to match, so `northwind platform` finds the platform lead at Northwind rather than everyone at Northwind and every platform engineer. Case and accents do not matter, so `emile`, `Émile` and `ÉMILE` all find Émile, and quotes around a word are ignored.
2. Results arrive grouped, up to six in each group:

| Group | What is searched | Choosing a result |
| --- | --- | --- |
| **Actions** | The names of the actions listed below | Runs it |
| **Posts** | The saved text and tags of every post, whatever its status, and the text of your posts imported from LinkedIn, marked PUBLISHED ON LINKEDIN | A draft opens in the **Composer**. A queued or scheduled post opens **Queue**. A published post, and a post imported from LinkedIn, opens **Analytics** |
| **Leads** | Name, company, headline and notes, and every comment the person left | Opens **Leads** with that person selected. A lead found by a comment shows the comment, starting "Commented:" |
| **Hook forms** | The hook, archetype and pacing pattern of each form | Opens the **Composer**, where the hook rail applies the form to your opening line |
| **Help** | The help articles in **Docs** | Opens the article at the section that matched |

3. Move with the arrow keys and press **Enter**, or click a result. The selected result shows where it will open, for example "Opens in Composer".

A group with more than six matches shows the first six. There is no "show more": add another word to narrow it.

## What happens

- Each search goes to the studio's own server on this computer. It reads the local database and the offline documentation index, and nothing else. The footer says **SEARCHES THIS MACHINE ONLY**, and nothing you type is sent anywhere. See [What leaves this machine, and when](what-leaves-this-machine.md).
- Posts are searched as they were last saved. Text you have typed in the Composer but not saved is not in the database yet, so it cannot be found.
- Only a draft is ever loaded into the Composer. The Composer holds one post, and **Save** writes over whichever post it holds, so a queued or published post opens where it is listed instead of in the editor.

## Opening a draft over unsaved text

If the Composer holds text you have not saved, choosing a different draft first asks: "The post in the Composer has unsaved changes. Open the other draft and discard them?"

- **Cancel** keeps your text where it is. Nothing else changes.
- **OK** replaces it with the draft you chose. The unsaved text is gone, because the studio does not autosave.

See [Start a new post, or find one you wrote earlier](start-a-new-post-or-find-an-earlier-one.md).

## Actions

With nothing typed, the box lists what it can do without searching:

- **Go to** each surface on the rail. **Go to Devtools** appears only when that surface, which is for whoever maintains the studio, is switched on.
- **Switch theme** changes between the light and dark themes, the same as the sun or moon button in the top bar. The studio remembers the choice in this browser; until you make one, it follows your computer's setting.
- **Show or hide the inspector** switches to the Composer and opens or closes the inspector.

Each action does what its label says. Earlier versions listed entries such as "Generate 5 hooks" and "Schedule at peak slot" that only switched screens; they have been removed.

## If it does not work

| You see | What it means |
| --- | --- |
| "Nothing in your posts, leads, hook forms or help matches that." | No saved item contains every word you typed. Try fewer words |
| "The search could not run" followed by a reason | The studio's server did not answer. See [The studio will not open](the-studio-will-not-open.md) |
| "Leads could not be searched." (or another group) | That one group failed. The other groups are still searched and shown |
| A post you just wrote is missing | It has not been saved yet. Press **Save** in the Composer, then search again |
| A lead is missing | Only people the browser extension captured are stored. See [Why is my lead list empty?](why-is-my-lead-list-empty.md) |
