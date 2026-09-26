# Search the help and the playbook in Docs
Find an answer in the studio's built-in help and playbook, and see what happens to what you type.

## Open Docs

Click **Docs** in the rail. You can also press **Ctrl+K** and choose **Search the playbook**, which only opens Docs; it does not run a search. See [Use the command palette (Ctrl+K)](use-the-command-palette.md).

## The home page

Docs opens on a page headed **What do you need to know?**. Below the search box you will find:

- **Get started**: cards for the first-steps articles, each with an estimated reading time.
- **Browse by topic**: one card per help topic, showing how many documents it holds and an estimated reading time.
- **Also in the library**: **For maintainers** and **Retired manuals and history**. These are kept for reference, not for everyday use.

The left column lists the same topics. Click a topic name to see its documents, or the arrow beside it to expand the list in place.

## Search

1. Type in the **Search every document** box, either on the home page or at the top of the left column.
2. Stop typing. Results appear by themselves a moment later; there is no button to press.
3. Read the results. The heading reads "N results for" your search. Documents whose title or file path contains your text, as typed, are listed first under **N documents by name**, then matching sections of text under **N passages** (up to 20).
4. Click a passage to open its document scrolled to the heading where the match was found. Click a name match to open the document at the top.
5. To clear the search, click the **X** at the right of the box in the left column, or delete the text. Click **All topics** to return to the home page.

## How matching works

| You type | What is searched |
| --- | --- |
| Several words | Passages that contain every one of the words |
| A short word such as `sched` | Also longer words that start with it, such as "schedule" and "scheduler" |
| Punctuation, symbols, or accented and non-English letters | Ignored, treated as spaces |

Help articles are listed before maintainer documents, and maintainer documents before retired manuals. Prefer a help article when both answer your question.

## Read a document

- The button at the top reads **ALL TOPICS**, or **BACK TO** the previous document's title if you followed a link from another document.
- Above the text you see the topic, the file path, the word count and an estimated reading time.
- Longer documents have an **In this document** list on the right when the window is wide enough. Click an entry to jump to it.
- A retired manual shows a **Kept for the record** notice saying it describes an earlier version of the studio and parts of it no longer match. Its **GO TO THE HELP TOPICS** button returns you to the home page. Do not rely on a retired manual where it disagrees with a help article.

## What happens

- Your search goes only to the studio's own server at `127.0.0.1` on this computer. Nothing is fetched from the internet and nothing is sent to an AI provider.
- The server looks your words up in a full-text index stored in the studio's local database. It builds the index when the studio starts, and rebuilds it on the next search if the documentation files have changed.
- The home page says "nothing you type is sent anywhere". That is true of the network, but your search does reach the local server, and the server window started by `launch_studio.bat` can print each request, including your search text. It stays on this computer.

For everything the studio does send, see [What leaves this machine, and when](what-leaves-this-machine.md).

## If it does not work

| What you see | What it means |
| --- | --- |
| OPENING THE LIBRARY | Docs is still loading the list of documents. If it stays, the server may be slow, or it returned no documents |
| THE DOCUMENTATION LIBRARY COULD NOT BE READ | The list of documents could not be fetched. Check the studio is running, then reopen Docs. See [The studio will not open](the-studio-will-not-open.md) |
| READING | The document is still loading |
| THIS DOCUMENT IS EMPTY | The file exists but has no content |
| Nothing matches that | No document contains every word you typed. Try fewer or shorter words. If the server has stopped, a failed search also shows this, so if every search returns nothing, check the studio is still running |
