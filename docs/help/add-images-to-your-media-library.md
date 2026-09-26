# Add images and files to your media library
Upload images, PDF carousels and videos, or generate a square image, and keep them in the studio's local media library.

## Open the library

1. Open **Composer** from the rail.
2. If the inspector is closed, click **Open inspector** at the top right.
3. Choose the **Media** tab.

The library lists every asset with its size, and its dimensions or page count where known. If it is empty you see NOTHING IN THE LOCAL LIBRARY YET.

## Upload

Drop one or more files on the box, or click **Drop a file, or click to choose**.

| Kind | Extensions | Stored as |
| --- | --- | --- |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp` | image, with width and height |
| PDF carousels | `.pdf` | carousel, with page count (recorded as 1 if the studio cannot read the PDF) |
| Video | `.mp4`, `.webm` | video |

The studio checks that each file is not empty and, for every type except `.webm`, that its opening bytes match its extension. Each file is handled on its own, so one bad file does not stop the others.

## Generate an image

1. Under **Generate an image**, type in **Describe the image**.
2. Click **Preview prompt** to see the full prompt the studio builds from your description.
3. Click **Generate**. The button shows a percentage and a bar fills below it, with the current stage in capitals.
4. When it finishes, the description clears and the new image appears in the library.

Every image is square (1:1). The percentages mark fixed stages, some with short built-in pauses, so they are not a measure of rendering work.

> [!TIP]
> A phrase in quotation marks in your description (6 to 120 characters) is drawn onto the image as a quote, attributed to "LEADERSHIP". Single quotes count too, so two apostrophes can turn the words between them into a quote. Naming Socrates, Marcus Aurelius, Steve Jobs or Seneca adds a fixed quote by that person instead.

## What happens

Generating is not fully local. Which services see your description depends on your AI settings (see [Connect your own AI provider](connect-your-own-ai-provider.md)):

| Your AI setup | Description sent to your AI provider | Image rendered by |
| --- | --- | --- |
| No key | No | image.pollinations.ai |
| `openai` | Yes | DALL-E 3, then Pollinations if that fails |
| `gemini` | Yes | Imagen 3, then Pollinations if that fails |
| Any other provider | Yes | Pollinations |

- With no key, Generate still sends a prompt built from your description to image.pollinations.ai, a third party. The prompt travels in the request address. Pollinations' watermark is cropped off.
- If `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set in your environment, Imagen 3 is tried even when Gemini is not your chosen provider.
- With a provider configured, **Preview prompt** also sends your description to it, and the model may word the scene differently at **Generate**.
- If every service fails, the studio draws a simple image locally instead.
- Starting the studio with `INOX_ALLOW_IMAGE_EGRESS=0` or `INOX_NO_EGRESS=1` blocks the image services. You then get the locally drawn image. The **Media** tab does not say a request was blocked. The refusal only appears as a count on the **image** line under **What has left this machine**, in **Brand Studio**, **Local security**.

Uploads never leave your machine.

## Current limits

- You cannot attach media to a post from the Composer. Drafts are saved as text only.
- The Brand Studio watermark setting is not applied to images generated here.

## Where files are kept

Files live in the studio's data home: uploads in `assets\uploads`, generated images in `assets\generated`. On Windows the data home is normally `%LOCALAPPDATA%\InoxHydra`. If your install keeps a `data` folder inside its `studio` folder, as the portable build does, the data home is that `studio` folder.

To delete an asset, hover over it in the library and click the bin icon. The file and its entry are removed. There is no confirmation step.

## If it does not work

| You see | What to do |
| --- | --- |
| `name: Unsupported file type '.gif'. Allowed: ...` | Convert the file to a listed type. |
| `name: Uploaded file is empty (0 bytes). Please upload a valid media file.` | The file has no content. Export it again. |
| `name: Invalid PDF format. The file content does not match the .pdf extension.` (or PNG, JPEG, WEBP, MP4) | The file was renamed from another format. Re-save it in the real format. |
| "Generation failed." or the reason it failed | The task stopped. Try again. |
| "Progress could not be read, so the outcome is unknown." | The studio stopped answering while you waited. The image may still arrive. Reopen the **Media** tab to check. |
| MEDIA LIBRARY UNAVAILABLE | The list could not be loaded. See [The studio will not open or shows an error](the-studio-will-not-open.md). |
| An asset stays after you delete it | A failed delete shows no message. Try again. |
