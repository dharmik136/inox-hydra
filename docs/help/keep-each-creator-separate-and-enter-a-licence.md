# Keep each creator separate, and enter a licence

Give each creator you write for a profile of their own, with nothing shared between them, and enter the licence key from your purchase.

## Each profile is its own studio

The profile switcher sits at the bottom of the rail. Each profile is a separate folder on this machine with its own database, media, backups and exports. Switching profile reloads the studio, and every screen then shows only that profile's posts, drafts, leads and analytics. Nothing one profile holds appears in another, and a backup or export made in one profile holds that profile alone.

Your first profile is the studio as it was before profiles existed, so its data stays where it always was. Every other profile lives in the `profiles` folder inside the studio's data home.

The licence, the logs and the bridge browser belong to the machine, so they are the same for every profile. Settings belong to the profile, including the AI provider and key: set them once in each profile, so each client can use their own. Scheduled posts in every profile still fall due when they should, whichever profile is open.

## Add a profile

1. Click the avatar at the bottom of the rail.
2. Click **Add Creator Profile**, give it a name, and click **Add Profile**.

The new profile opens straight away, empty. To fill it, go through **Setup** in it, with that creator's own LinkedIn in the bridge browser.

More than one profile needs the Agency licence. Without it, **Add Profile** shows "Your licence covers 1 creator profile."

## Delete a profile

Deleting a profile removes its folder: its database, media, backups and exports. It cannot be undone, so export it first if you might want it later. See [Back up, restore and export your data](back-up-restore-and-export.md).

1. Switch to another profile. The open profile cannot be deleted, and neither can your first one.
2. Open the switcher, point at the profile, and click the bin icon.
3. Type the profile's name, then click **Delete profile**.

## Enter a licence

1. Open **Brand Studio**, then **Licence**.
2. Paste the key from your purchase email into **Enter a licence**. It begins `IHL1.`
3. Click **Use this licence**.

The key is checked on this machine, against the key the studio ships with. Nothing is sent anywhere to check it, and it works offline. **This machine** then shows the tier, who the licence is for, and when it ends. A key that has already ended is refused, so it cannot replace one that works.

| Tier | Price | What it adds |
| --- | --- | --- |
| Free | Nothing | The composer, the fold simulator, the audit, hooks from templates, and export. |
| Creator | $12 a month billed yearly ($144), or $249 once with a year of updates | Analytics, leads, Today, patterns, AI with your own key, the Obsidian export and the archive import. |
| Agency | $39 a month | Up to 5 creator profiles, each with every Creator feature. |

During the beta every Creator feature is open on every install, licensed or not. A licence changes one thing today: the number of profiles.

A licence has an end date, apart from a lifetime one. Each renewal sends a new key with a new end date; paste it the same way. The studio remembers the latest date it has seen, so setting the computer's clock back does not bring an ended licence back. When the clock reads earlier than that date, **This machine** names the date the licence is checked against. When a licence ends, the studio returns to the free tier. Nothing is deleted, and everything stays readable and exportable. **Remove licence** takes the key off this machine, for example before you hand the computer on.

### When an Agency licence ends

Your first profile always works. The profiles beyond what the licence now covers, counted in the order you made them, stay closed: the studio opens your first profile instead, their scheduled posts wait, and clicking one in the switcher shows why and how to renew. They are still listed, and nothing in them is deleted. You can still back one up or export it from the command line, for example `python -m studio.cli backup --profile <profile id>` (portable copy: `InoxHydra-CLI.bat backup --profile <profile id>`), or delete it. Paste a renewed key and they open again.
