# After an update, reload the browser extension
You do not re-install or re-pair the extension after an update, but if you loaded it by hand you must reload it, and load it again from the new folder if the folder moved.

## Why this is needed

The extension, listed on your browser's extensions page as **LinkedIn Studio Bridge (LocalTaplio)**, is an unpacked folder that ships inside the studio, in `studio/extension`. Its version number is kept equal to the studio's (2.5.2 in this build). The studio never updates the copy your browser has loaded, and it does not warn you when the two versions differ.

## Which case are you

| How you loaded it | How you updated | What to do |
| --- | --- | --- |
| From the launcher on Setup or Leads | Any | Close the bridge browser and open it again from the launcher |
| Load unpacked | Source checkout updated in place | Reload the extension |
| Load unpacked | Portable folder deleted and the new ZIP extracted | Remove the extension and load it again from the new folder |
| Load unpacked | Desktop app | Check the folder path again, then reload, or remove and load again |

## If you use the launcher

1. Close every window of the browser the studio opened for the bridge. It runs in its own profile, separate from your usual one.
2. In the studio, open **Setup** and, in step 1 **Connect the browser**, click **Open LinkedIn with the bridge**. Or, while your lead list is empty, open **Leads** and click your browser under **OPEN LINKEDIN WITH THE BRIDGE**.

What happens: the launcher starts the browser with the extension loaded from the current install's folder every time, so the new version comes with it. It also opens the studio in a second tab, which keeps the browser paired.

**Open LinkedIn with the bridge** shows only while step 1 is not connected. Step 1 counts as connected for 150 seconds after the extension's last heartbeat, so after closing the old window, wait up to two and a half minutes if the button has not appeared. The launcher does not work with Google Chrome, which ignores the flag it uses; see [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

## If you loaded it by hand

1. Open your browser's extensions page (`edge://extensions` in Edge, `brave://extensions` in Brave).
2. Find **LinkedIn Studio Bridge (LocalTaplio)** and click **Reload**. Do this even if the files changed in place, to be sure the browser uses the new ones.
3. If the folder it was loaded from no longer exists, **Remove** the extension, choose **Load unpacked** and select the new folder.
4. Reload any LinkedIn tabs that were open. A LinkedIn page opened before the reload cannot reach the studio until it is reloaded too.

A portable folder is named after its version, for example `InoxHydra-2.5.2-win64`. The upgrade steps in [Check your version and update the studio](check-your-version-and-update-the-studio.md) have you delete the old folder and extract the new ZIP, so unless you renamed it, a hand-loaded extension now points at a folder that is gone. In the new folder, use `app\studio\extension`: that is the path the studio's own launcher uses. The ZIP also has a second copy in `extension` at the top of the folder.

To get the exact path, open **Leads** and click **Copy the folder path** under **OR LOAD IT BY HAND**. The path is also printed under the button. This section appears only while your lead list is empty, and only when the studio found at least one Chromium browser. For the desktop app, the extension sits inside the app's installed files; this guide does not say whether that path changes on update, so copy it again and compare.

Removing the extension loses nothing: it keeps no data of its own in the browser.

## Pairing survives the update

The studio's access token is kept in a `vault` folder with your data, not in the application files, so replacing the application folder does not unpair the extension. There are two exceptions where the vault sits beside the code:

- In a source checkout with a `studio/data` folder, the vault is `studio/vault`, which the upgrade steps tell you to keep.
- In true portable mode (you created a `data` folder inside `app\studio`), the vault is `app\studio\vault`, inside the folder you delete to upgrade. Copy it out with your data, or pair again afterwards.

The browser holds the token as a cookie that lasts a year. An extension loaded from a new folder gets a new ID, and the studio still accepts it; the token is what authorises it.

You need to pair again only if the token changed or the browser lost the cookie: after `python -m studio.cli token reset`, which prints "Reload the studio in your browser, and reload the extension.", after the vault folder was lost, on a different machine, or after clearing cookies. To pair, open `http://127.0.0.1:8000` once in the same browser, and the same profile, that runs the extension. The launcher's second tab does this for you.

## Check it

1. In the bridge browser, open a LinkedIn tab and keep it in view. The extension reports its version when the page loads and then about once a minute while the tab is visible.
2. In **Setup**, step 1 reads "Connected, extension 2.5.2", with your version.
3. Open `http://127.0.0.1:8000/api/v1/health` and compare the `version` it shows. The two should match. Nothing compares them for you.

## If it does not work

| What you see | What to do |
| --- | --- |
| Step 1 shows the old version | A browser is still running the old files. Reload the extension, or remove it and load the new folder, then reload the LinkedIn tab. Step 1 shows the version from the most recent heartbeat, so check any other browser that still has the old copy loaded. |
| "Last heard from ... Open a LinkedIn tab in the bridge browser." | No visible LinkedIn tab, the extension failed to load, or this browser is no longer paired. Check the extensions page for an error, and open `http://127.0.0.1:8000` in that browser. |
| The extensions page cannot find the folder | It moved. Remove the extension and load it again from the new path. |
| "LinkedIn Studio: could not reach your studio, so nothing was saved." | The studio is not running, this browser is not paired, or the tab was open before you reloaded the extension. Reload the tab, and open `http://127.0.0.1:8000` in that browser. |
| Leads stay empty | See [Why is my lead list empty?](why-is-my-lead-list-empty.md). |

For the rest of Setup, see [Set up the studio from your own LinkedIn](set-up-the-studio-from-your-linkedin.md).
