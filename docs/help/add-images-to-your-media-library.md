# Add images and files to your media library
Upload images, PDF carousels and videos, or generate a square image with the image provider you choose, and keep them in the studio's local media library.

## Open the library

1. Open **Composer** from the rail.
2. If the inspector is closed, click **Open inspector** at the top right.
3. Choose the **Media** tab.

The library lists every asset with its size, and its dimensions or page count where known. If it is empty you see NOTHING IN THE LOCAL LIBRARY YET.

## Upload

Drop one or more files on the box, or click **Drop a file, or click to choose**. The box says the files are kept on this computer: to use one in a post, add it on LinkedIn (see Current limits below).

| Kind | Extensions | Stored as |
| --- | --- | --- |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp` | image, with width and height |
| PDF carousels | `.pdf` | carousel, with page count (recorded as 1 if the studio cannot read the PDF) |
| Video | `.mp4`, `.webm` | video |

The studio checks that each file is not empty and, for every type except `.webm`, that its opening bytes match its extension. Each file is handled on its own, so one bad file does not stop the others.

## Generate an image

1. Under **Generate an image**, the line under the heading says who makes the image and where the prompt goes, for example "Made by Free public generator (image.pollinations.ai), flux." To change it, see **Choose who makes your images** below.
2. Type in **Describe the image**.
3. Click **Preview prompt** to see the full prompt the studio builds from your description.
4. Click **Generate**. The button shows a percentage and a bar fills below it, with the current stage in capitals.
5. When it finishes, the description clears, "Added to the library." appears, and the new image is in the library.

Every image is square (1:1), 1080 by 1080 pixels, whatever size the provider made it. The percentages mark the stages the studio passes through, not rendering work.

If generation fails, the reason appears in orange, such as "OpenAI Images refused the key (HTTP 401)" or "Nothing was sent to Free public generator (image.pollinations.ai): INOX_NO_EGRESS is set". Nothing is added to the library. The studio never draws a stand-in image in place of one that failed.

> [!TIP]
> A phrase in quotation marks in your description (6 to 120 characters) is drawn onto the image as a quote, with no name under it unless you give one. Single quotes count too, so two apostrophes can turn the words between them into a quote. Naming a person adds no quote of theirs: the studio only draws words you typed.

### Quotes in Hindi, Gujarati and other scripts

The studio carries its own fonts for quotes and your watermark: Noto Sans (Latin, Greek and Cyrillic letters), Noto Sans Devanagari and Noto Sans Gujarati. For other scripts, such as Tamil, Bengali, Arabic or Chinese, it uses a font your computer has.

A quote is never drawn with boxes in place of letters. When it cannot be drawn correctly, the image is still saved without it, and the message under the bar says why:

| Message | What it means |
| --- | --- |
| The quote was not drawn: no font on this computer has these letters | Install a font for that script, such as the matching Noto Sans font, then generate again. |
| The quote was not drawn: this computer's Pillow cannot lay out this script | Hindi, Gujarati, Arabic and other scripts whose letters join or change order need a text layout library (FriBiDi) that this install does not have. This is usual on Windows. Drawn without it, the letters would be in the wrong order, so the studio does not draw them. Latin text is not affected. |
| Emoji are left out of the drawn text | Emoji cannot be drawn at quote size. The rest of the quote is drawn. |

## Choose who makes your images

The image provider is set per profile, in the **Prompt** tab under **Images**, below your AI provider.

1. Open **Composer**, open the inspector, and choose the **Prompt** tab.
2. Under **Images**, read what is set now: **Generate** (the provider), **Model**, **Set by** (chosen here, your AI provider's key, or the default), **Key** (its last four characters only), **Checked** (when the studio last checked it) and **Egress** (whether the prompt leaves this computer).
3. Under **Change image provider**, choose one. The box below the list says what leaves this machine with that choice, to whom, and on whose account, before you save anything.
4. Fill in what it asks for: a key for a cloud account, the address for a web UI on your own machine, and the model if you want another one than shown.
5. Click **Verify and save** (or **Save** where there is nothing to check). The studio checks the setup without making an image, then shows the model, for example "OpenAI accepted the key. Model: gpt-image-1." If the check fails, the reason is shown and the previous setup stays.

| Choice | What leaves this machine | Account | Checked by |
| --- | --- | --- | --- |
| **Free public generator (image.pollinations.ai)** (the default) | The image prompt and size, inside the web address of the request, to a free public service run by a third party | None | Nothing to check |
| **OpenAI Images** (gpt-image-1, dall-e-3) | The image prompt and size, with your key, to api.openai.com | Yours, billed per image. gpt-image-1 works only after OpenAI has verified your organisation, and is priced differently from dall-e-3 | Asking OpenAI for the model |
| **Google Imagen (Gemini API)** (Imagen 4, Imagen 3) | The image prompt and size, with your key, to generativelanguage.googleapis.com | Your Google AI Studio key, with billing on | Asking Google for the model, and listing its Imagen models |
| **Stability AI** (Stable Image Core and Ultra, SD 3.5) | The image prompt, the things to avoid, and the size, with your key, to api.stability.ai | Yours, spends credits | Reading your credit balance |
| **Replicate** (FLUX and other models, written owner/name) | The image prompt and size, with your key, to api.replicate.com; the image is then downloaded from Replicate's file host, without your key | Yours, billed per image | Asking Replicate for the model |
| **fal.ai** (FLUX) | The image prompt and size, with your key, to fal.run | Yours, billed per image | Not checked: fal.ai cannot check a key without making an image. The first Generate checks it. |
| **Together AI** (FLUX) | The image prompt and size, with your key, to api.together.xyz | Yours, billed per image | Listing your image models |
| **AUTOMATIC1111 or Forge web UI** | The image prompt, the things to avoid, and the size, to the address you enter | Your own machine. Start the web UI with the `--api` option. | Reading its loaded model and model list |
| **ComfyUI** | The same, as a basic text-to-image workflow, to the address you enter | Your own machine. It uses a checkpoint from ComfyUI's models/checkpoints folder. | Listing its checkpoints |
| **Off** | Nothing. **Generate** is turned off. | None | Nothing to check |

- With nothing chosen, an `openai` or `gemini` AI provider's key makes the images with the model it used before this setting existed (`dall-e-3` or `imagen-3.0-generate-002`), and **Set by** says "Your AI provider's key". The model changes only when you choose another one here. A new setup starts on the newer model, and the line under **Model** says what it needs or costs. Otherwise the free public generator is used. To use the AI provider's key on purpose, choose the same company and leave the key empty.
- A web UI address on this computer (`127.0.0.1` or `localhost`) keeps the prompt here, and works even when outbound requests are switched off. An address on your network is another computer, and the prompt leaves this one for it. An address on the internet must start with `https`.
- Only the provider you chose is asked. If it fails, the generation fails; the studio does not try another service in its place.
- With an AI provider set up, **Preview prompt** and **Generate** also send your description to that AI provider first, to write the scene (see [Connect your own AI provider](connect-your-own-ai-provider.md)).
- A key is stored in this machine's encrypted vault and never shown again in full. Leave the key empty when you change only the model, and the saved key is kept.
- The free public generator's mark is cropped off the image.
- Starting the studio with `INOX_ALLOW_IMAGE_EGRESS=0` or `INOX_NO_EGRESS=1` blocks every image provider that is not on this computer. **Generate** then fails, saying nothing was sent and which setting blocked it, and the **image** line under **What has left this machine** in **Brand Studio**, **Local security**, counts the refusal.

Uploads never leave your machine.

## Current limits

- You cannot attach media to a post from the Composer. Drafts are saved as text only.
- The Brand Studio watermark setting is not applied to images generated here.

## Where files are kept

Files live in the studio's data home: uploads in `assets\uploads`, generated images in `assets\generated`. On Windows the data home is normally `%LOCALAPPDATA%\InoxHydra`. If your install keeps a `data` folder inside its `studio` folder, as the portable build does, the data home is that `studio` folder.

To delete an asset, click the bin icon beside it in the library and confirm. The file and its entry are removed from this computer. If the delete fails, the reason is shown in orange above the library and the asset stays listed.

## If it does not work

| You see | What to do |
| --- | --- |
| `name: Unsupported file type '.gif'. Allowed: ...` | Convert the file to a listed type. |
| `name: Uploaded file is empty (0 bytes). Please upload a valid media file.` | The file has no content. Export it again. |
| `name: Invalid PDF format. The file content does not match the .pdf extension.` (or PNG, JPEG, WEBP, MP4) | The file was renamed from another format. Re-save it in the real format. |
| The reason it failed, in orange, after **Generate** | Nothing was added to the library. A key or model problem: fix it under **Images** in the **Prompt** tab. "Could not reach" or "had a problem of its own": try again later. "Nothing was sent": outbound image requests are switched off on this computer. |
| "Image generation is off." and **Generate** cannot be clicked | Choose an image provider under **Images** in the **Prompt** tab. |
| "Nothing answered at http://127.0.0.1:7860" | The web UI is not running at that address. Start it (AUTOMATIC1111 and Forge with `--api`), then try again. |
| "Progress could not be read, so the outcome is unknown." | The studio stopped answering while you waited. The image may still arrive. Reopen the **Media** tab to check. |
| MEDIA LIBRARY UNAVAILABLE | The list could not be loaded. See [The studio will not open or shows an error](the-studio-will-not-open.md). |
| An asset stays after you delete it, with a reason in orange | The studio could not remove the file. Read the reason, then try again. |
