# After an update, the browser extension reloads itself
From version 2.10, an update needs nothing from you in the browser when the extension is loaded from the folder the studio was updated in: the extension notices that its files changed, reloads itself, and gives the LinkedIn tabs already open its new readers, so no tab needs a refresh either. You reload or load it again by hand only in the cases below, and Health says when one applies.

## How it updates itself

The extension, listed on your browser's extensions page as **Inox Hydra Bridge** (versions before 2.6 called it **LinkedIn Studio Bridge (LocalTaplio)**, and it takes the new name when it reloads), is an unpacked folder that ships inside the studio, in `studio/extension`. Its version number is kept equal to the studio's.

When the browser starts, and every five minutes after that, the extension reads the version written in its own folder's `manifest.json` and compares it with the version it is running. When they differ, it reloads itself from the folder. It also looks at once when the studio answers its check-in with a different version, so after an update in place it usually reloads within a minute of the studio restarting.

When it is installed or updated, it starts its readers in the LinkedIn tabs already open, as a reload of each tab would. A tab it cannot reach is counted, and Health then says "N LinkedIn tabs still carry an older copy of the bridge's readers, which the update could not replace: reload them." Reload those tabs; the extension itself is fine.

Updating to 2.10.2 also retires network reading. The update removes the script an earlier version had registered in the browser to read LinkedIn's network responses, and the stored switch, with no reload needed. A LinkedIn tab that was open with the switch on keeps the old wrapper, which sends nothing anywhere, until you reload or close that tab.

Two limits:

- It compares version numbers. A change to its files that keeps the same version, such as a source checkout between two releases, still needs **Reload** on the extensions page.
- It was checked in Chromium with developer mode on, which **Load unpacked** needs and which the studio's launcher turns on in its own browser profile. Leave developer mode on: with it off, the reload unloaded the extension instead, and you would have to load it again.

## Which case are you

| How you loaded it | How you updated | What to do |
| --- | --- | --- |
| Any | From a version before 2.10 | Reload it once by hand (below). From then on it reloads itself |
| From the launcher on Setup or Leads | Source checkout or desktop app updated in place | Nothing |
| From the launcher on Setup or Leads | Portable folder deleted and the new ZIP extracted | Close the bridge browser and open it again from the launcher |
| Load unpacked | Source checkout updated in place | Nothing |
| Load unpacked | Portable folder deleted and the new ZIP extracted | Remove the extension and load it again from the new folder |
| Load unpacked | Desktop app | Check the folder path again; if it changed, remove the extension and load it again |

## What Health says, and when

Health's line under the title says to act only when a reload, by itself, will not happen:

| Health says | What to do |
| --- | --- |
| "This browser runs Inox Hydra Bridge 2.9.0, older than the studio's 2.10.0, and that version cannot reload itself. ..." | A version from before 2.10. Reload it once by hand |
| "The folder this browser loaded Inox Hydra Bridge 2.10.0 from is no longer there, ..." | The folder was deleted or moved, as a portable upgrade does. The extension runs on from memory but cannot update itself, and the browser will not load it when it next starts. Load it again from the studio's folder |
| "This browser loads Inox Hydra Bridge 2.10.0 from a folder that is not this studio's, which runs 2.11.0, ..." | It is loaded from an older install's folder, which the update did not change. Load it again from the studio's folder |
| "N LinkedIn tabs still carry an older copy of the bridge's readers, ..." | Reload those tabs |
| Nothing about the extension | Nothing to do |

When the bridge runs in more than one browser, Health lists each one under the line, and a browser whose folder is gone says so there. Setup's step 5 and **Today** say to reload the extension before importing again only while the bridge they last heard from still needs it.

## If you use the launcher

1. Close every window of the browser the studio opened for the bridge. It runs in its own profile, separate from your usual one.
2. In the studio, open **Setup** and, in step 1 **Connect the browser**, click **Open LinkedIn with the bridge**. Or, while your lead list is empty, open **Leads** and click your browser under **OPEN LINKEDIN WITH THE BRIDGE**.

What happens: the launcher starts the browser with the extension loaded from the current install's folder every time, so the new version comes with it. It also opens the studio in a second tab, which keeps the browser paired.

**Open LinkedIn with the bridge** shows only while step 1 is not connected. Step 1 counts as connected for 150 seconds after the extension's last check-in, so after closing the old window, wait up to two and a half minutes if the button has not appeared. The launcher does not work with Google Chrome, which ignores the flag it uses; see [Install the browser extension that captures leads and analytics](install-the-browser-extension.md).

## If you load it by hand

To reload it once, after updating from a version before 2.10:

1. Open your browser's extensions page (`edge://extensions` in Edge, `brave://extensions` in Brave).
2. Find **Inox Hydra Bridge** and click **Reload**.

The LinkedIn tabs already open get the new readers by themselves. A version before 2.10 could not do that, so if Health names tabs that still carry the older readers, reload those tabs.

To load it again from a new folder:

1. On the extensions page, **Remove** Inox Hydra Bridge.
2. Choose **Load unpacked** and select the extension folder of the studio you now run.

A portable folder is named after its version, for example `InoxHydra-2.10.0-win64`. The upgrade steps in [Check your version and update the studio](check-your-version-and-update-the-studio.md) have you delete the old folder and extract the new ZIP, so unless you renamed it, a hand-loaded extension now points at a folder that is gone. In the new folder, use `app\studio\extension`: that is the path the studio's own launcher uses. The ZIP also has a second copy in `extension` at the top of the folder.

To get the exact path, open **Leads** and click **Copy the folder path** under **OR LOAD IT BY HAND**. The path is also printed under the button. This section appears only while your lead list is empty, and only when the studio found at least one Chromium browser. For the desktop app, the extension sits inside the app's installed files; this guide does not say whether that path changes on update, so copy it again and compare. If it changed, Health says the folder is gone or is not the studio's.

Removing the extension loses only what it holds in the browser: captures still waiting for the studio, which **Today** counts, and any held for a LinkedIn account no creator profile has confirmed, which Health counts. Let those be sent first when you can.

## Pairing survives the update

The studio's access token is kept in a `vault` folder with your data, not in the application files, so replacing the application folder does not unpair the extension. There are two exceptions where the vault sits beside the code:

- In a source checkout with a `studio/data` folder, the vault is `studio/vault`, which the upgrade steps tell you to keep.
- In true portable mode (you created a `data` folder inside `app\studio`), the vault is `app\studio\vault`, inside the folder you delete to upgrade. Copy it out with your data, or pair again afterwards.

The browser holds the token as a cookie that lasts a year. An extension loaded from a new folder gets a new ID, and the studio still accepts it; the token is what authorises it.

You need to pair again only if the token changed or the browser lost the cookie: after `python -m studio.cli token reset`, which prints "Reload the studio in your browser, and reload the extension.", after the vault folder was lost, on a different machine, or after clearing cookies. To pair, open `http://127.0.0.1:8000` once in the same browser, and the same profile, that runs the extension. The launcher's second tab does this for you.

## Check it

1. The extension checks in with the studio about once a minute from its background worker while the browser is open, whether or not a LinkedIn tab is, and at once when a LinkedIn page opens. A version before 2.10 checked in only from an open LinkedIn tab.
2. In **Setup**, step 1 reads "Connected, extension 2.10.0", with your version.
3. Open `http://127.0.0.1:8000/api/v1/health` and compare the `version` it shows. The two should match, or match within five minutes of an update. Health compares them too, and says so only when you need to act.

## If it does not work

| What you see | What to do |
| --- | --- |
| Step 1 shows the old version, and Health says nothing | The extension is updating itself: give it up to five minutes. If it stays, check that developer mode is on, and that the update changed the version number |
| Step 1 shows the old version, and Health says to reload or load it again | Do what Health says, as in **What Health says, and when** above. Step 1 shows the version from the most recent check-in, so check any other browser that still has an old copy loaded |
| "Last heard from ... Open a LinkedIn tab in the bridge browser." | The bridge browser is closed, the extension failed to load, or this browser is no longer paired. Open the browser and a LinkedIn tab, check the extensions page for an error, and open `http://127.0.0.1:8000` in that browser |
| The extensions page cannot find the folder | It moved. Remove the extension and load it again from the new path |
| "Inox Hydra: could not reach your studio, so nothing was saved." | The studio is not running, or this browser is not paired. Open `http://127.0.0.1:8000` in that browser. A tab open since before an update to 2.10 needs reloading once |
| Leads stay empty | See [Why is my lead list empty?](why-is-my-lead-list-empty.md) |

For the rest of Setup, see [Set up the studio from your own LinkedIn](set-up-the-studio-from-your-linkedin.md).
