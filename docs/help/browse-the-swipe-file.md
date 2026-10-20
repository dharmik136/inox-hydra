# Browse the Swipe File
Read the hook forms in the Swipe File, filter them by type, and see where they come from.

## What it is

The **Swipe File** is a wall of hook forms: opening lines, each paired with the structure that follows it. They are patterns to borrow, not posts that anybody published and measured. The banner at the top of the wall says so:

> These are hook forms, not posts anyone measured. Velocity rates how strongly the shape performs. No reactions or comments are shown because none were recorded: the studio stores the pattern, not an event.

## Read a specimen

Each card on the wall is one specimen.

| Part of the card | What it shows |
| --- | --- |
| Top line, in capitals | The type of hook, for example LESSON or HOW-TO |
| Second line, in larger type | The opening line itself |
| Blue line, in capitals | The structure behind it, for example PROMISE IN THE FIRST LINE, NUMBERED STEPS, ONE SENTENCE EACH |
| Bottom line | STARTER FORM, NOT RATED for a starter form. A form from the engineering creator pack shows EDITOR'S RATING and a number such as 9.8, then ENGINEERING PACK |
| Extra tag after the rating | SYNCED or IMPORTED, only when the specimen is recorded as having arrived by a sync or an import. Shipped specimens, and older rows with no recorded origin, carry no tag |

Hover over a card to expand it. The expanded text is the opening line and the structure again, as ordinary body text; there is nothing else hidden. Cards expand only on mouse hover, so with a keyboard or a touch screen you read the same content from the lines already visible.

> [!NOTE]
> Starter forms carry no rating. The editor's rating on an engineering pack form is a fixed number its author wrote, between 8.2 and 9.8. It is an editorial rating, not something calculated from your posts or from anything the studio captured.

## Find a specimen

1. Open **Swipe File** from the rail. To go straight to one specimen, press **Ctrl+K**, type a word from its hook, and choose it: Swipe File opens with that card outlined. See [Search everything with Ctrl+K](use-the-command-palette.md).
2. Type in **Search specimens**. The wall narrows as you type, matching the opening line, the structure and the type.
3. Press a type chip to show one type only: **All**, **Contrarian**, **How-to**, **Lesson**, **List**, **Question** or **Story**, and the engineering pack's types when it is added.
4. The count at the top right, for example **2 OF 12**, tells you how many cards are showing out of the whole library.

The search and the chips work together, and both filter in your browser.

## Where the specimens come from

A new studio starts with 12 starter forms, two of each type. Each is a fill-in shape with words in [brackets] to replace, and none claims anything about you until you fill it in. They are written into the local database when the library is read and found empty. Nothing is downloaded to do this.

### The engineering creator pack

The studio also carries 36 hook forms written for a software engineering audience, in six types (Architecture, Benchmarks, Contrarian Truths, Economics, Failure Analysis, Reverse Engineering). They are not in a new library. To add them, press **Add the engineering pack** under the banner; to take them out again, press **Remove the engineering pack**. Removing takes out only those 36 forms.

> [!CAUTION]
> Several pack forms are first-person claims, such as a cost, a percentage or a benchmark. They are true only of whoever makes them true. Change them to your own facts before you post.

A studio that already held these 36 forms before this version keeps them.

The **Hook rail** above the editor in the **Composer** reads the same library and shows its first 12 forms: rated forms first, then the starter forms.

## Use one in a post

Open **Composer** and apply the form from the **Hook rail**, or copy the text from the card. See [Try a different opening line](try-a-different-opening-line.md).

## Can I add my own?

Not from the interface. There is no add, save or delete control on the wall, and no command-line command for it.

The server has two routes that replace the library, and nothing in the interface calls either of them:

- An import, which loads a bundle of hook forms sent to the route as JSON. Those cards are tagged IMPORTED.
- A sync, which downloads a bundle from GitHub. Those cards are tagged SYNCED. This is the library category in [What leaves this machine, and when](what-leaves-this-machine.md).

> [!WARNING]
> When either route succeeds, it deletes the whole library, including the shipped forms, before writing the new one. It does not add to it.

On an older install whose original inspirations table still holds rows, the wall shows those rows instead of the hook library.

## If it does not work

| What you see | What it means |
| --- | --- |
| LOADING SPECIMENS | The wall is still reading the library. It loads once, when you open the surface. |
| SWIPE FILE UNAVAILABLE | The request failed. Open another surface and come back, or reload the page. |
| NO SPECIMENS SAVED YET | The library came back empty. See [Why is my analytics chart or Swipe File empty?](why-is-analytics-or-the-swipe-file-empty.md) |
| NOTHING MATCHES THAT | Your search and chip together match no card. Clear **Search specimens** or press **All**. |
