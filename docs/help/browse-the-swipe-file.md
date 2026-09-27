# Browse the Swipe File
Read the hook forms in the Swipe File, filter them by type, and see where they come from.

## What it is

The **Swipe File** is a wall of hook forms: opening lines, each paired with the structure that follows it. They are patterns to borrow, not posts that anybody published and measured. The banner at the top of the wall says so:

> These are hook forms, not posts anyone measured. Velocity rates how strongly the shape performs. No reactions or comments are shown because none were recorded: the studio stores the pattern, not an event.

## Read a specimen

Each card on the wall is one specimen.

| Part of the card | What it shows |
| --- | --- |
| Top line, in capitals | The type of hook, for example CONTRARIAN TRUTHS |
| Second line, in larger type | The opening line itself |
| Blue line, in capitals | The structure behind it, for example 1-LINE CONFESSION HOOK + BLANK LINE + 2-LINE CONTEXT + 3-POINT REVELATION |
| Bottom line | VELOCITY and a score such as 9.8 |
| Extra tag after the score | SYNCED or IMPORTED, only when the specimen is recorded as having arrived by a sync or an import. Shipped specimens, and older rows with no recorded origin, carry no tag |

Hover over a card to expand it. The expanded text is the opening line and the structure again, as ordinary body text; there is nothing else hidden. Cards expand only on mouse hover, so with a keyboard or a touch screen you read the same content from the lines already visible.

> [!NOTE]
> The velocity score is a fixed number written into the studio's shipped library, between 8.2 and 9.8. It is an editorial rating, not something calculated from your posts or from anything the studio captured.

## Find a specimen

1. Open **Swipe File** from the rail, or press **Ctrl+K** and choose **Find a similar specimen**, which only opens this surface.
2. Type in **Search specimens**. The wall narrows as you type, matching the opening line, the structure and the type.
3. Press a type chip to show one type only: **All**, **Architecture**, **Benchmarks**, **Contrarian Truths**, **Economics**, **Failure Analysis** or **Reverse Engineering**.
4. The count at the top right, for example **6 OF 36**, tells you how many cards are showing out of the whole library.

The search and the chips work together, and both filter in your browser.

## Where the specimens come from

The studio ships with 36 hook forms, six of each type. They are written into the local database when the server starts with an empty library, and again whenever the library is read and found empty. Nothing is downloaded to do this.

The **Hook rail** above the editor in the **Composer** reads the same library and shows its 12 highest-rated forms.

## Use one in a post

Open **Composer** and apply the form from the **Hook rail**, or copy the text from the card. See [Try a different opening line](try-a-different-opening-line.md).

## Can I add my own?

Not from the interface. There is no add, save or delete control on the wall, and no command-line command for it.

The server has two routes that replace the library, and nothing in the interface calls either of them:

- An import, which loads a bundle of hook forms sent to the route as JSON. Those cards are tagged IMPORTED.
- A sync, which downloads a bundle from GitHub. Those cards are tagged SYNCED. This is the library category in [What leaves this machine, and when](what-leaves-this-machine.md).

> [!WARNING]
> When either route succeeds, it deletes the whole library, including the 36 shipped forms, before writing the new one. It does not add to it.

On an older install whose original inspirations table still holds rows, the wall shows those rows instead of the hook library.

## If it does not work

| What you see | What it means |
| --- | --- |
| LOADING SPECIMENS | The wall is still reading the library. It loads once, when you open the surface. |
| SWIPE FILE UNAVAILABLE | The request failed. Open another surface and come back, or reload the page. |
| NO SPECIMENS SAVED YET | The library came back empty. See [Why is my analytics chart or Swipe File empty?](why-is-analytics-or-the-swipe-file-empty.md) |
| NOTHING MATCHES THAT | Your search and chip together match no card. Clear **Search specimens** or press **All**. |
