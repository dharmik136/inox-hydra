//! The desktop shell.
//!
//! What this adds over opening a browser at a port number: a window that is
//! the application rather than a tab, an icon and a taskbar entry of its own,
//! a tray the studio lives in while it is not on screen, and one instance no
//! matter how many times the user clicks the shortcut.
//!
//! What it deliberately does not add: any product behaviour. The window points
//! at the same local server the browser would, so a creator who prefers the
//! browser, or who needs the extension's LinkedIn capture, loses nothing by
//! never installing this.
//!
//! Startup order matters and is the reason this file is not shorter:
//!
//!   1. Claim single instance, or hand off to the copy already running.
//!   2. Start the backend, or discover it is already up.
//!   3. Wait for the health endpoint, showing a splash while that happens.
//!   4. Only then point the window at the studio and reveal it.
//!
//! Skipping step 3 is the common mistake. The window appears instantly and
//! shows a connection error, because binding a port finishes long before the
//! database has migrated.
//!
//! Strict Invariants:
//! - Zero em-dashes.
//! - Closing the window hides it. Quitting is an explicit act from the tray.
//! - The backend is stopped on exit only if this process started it.

mod backend;

use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, RunEvent, WindowEvent};

/// How long to wait for the backend before giving up and telling the user.
/// Generous on purpose: a first run applies migrations and builds the docs
/// search index, and an underpowered machine can take a while.
const READY_TIMEOUT: Duration = Duration::from_secs(45);

const MAIN_WINDOW: &str = "studio";

struct BackendState(Mutex<Option<backend::Backend>>);

fn show_studio(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW) {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

pub fn run() {
    tauri::Builder::default()
        // A second launch must not start a second engine that loses the race
        // for port 8000 and leaves the user with a window controlling nothing.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_studio(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();

            // Registered, and allowed to fail.
            //
            // The plugin needs plugins.updater in the configuration, and that
            // block is written at build time only when a public key is
            // available. A build without one must still produce a working
            // application, so a registration failure is recorded and stepped
            // over rather than propagated. The tray item then reports that
            // updates are not configured, which is the truth.
            #[cfg(desktop)]
            if let Err(error) = handle.plugin(tauri_plugin_updater::Builder::new().build()) {
                eprintln!("[shell] updates are not available in this build: {}", error);
            }

            build_tray(app)?;

            let resources = app
                .path()
                .resource_dir()
                .map_err(|e| format!("could not resolve the bundled payload: {}", e))?;

            match backend::start(&resources) {
                Ok(started) => {
                    let state = app.state::<BackendState>();
                    *state.0.lock().unwrap() = Some(started);
                }
                Err(message) => {
                    // Visible in a debug build only. A release build has no
                    // stderr, so this is a breadcrumb for a developer rather
                    // than a message to the user. What the user sees is the
                    // splash failing to resolve, which the splash itself
                    // explains after twelve seconds.
                    eprintln!("[shell] {}", message);
                }
            }

            // Off the main thread, because blocking setup would freeze the
            // splash window we are showing precisely so the user can see that
            // something is happening.
            std::thread::spawn(move || {
                let ready = backend::wait_until_ready(READY_TIMEOUT);

                if let Some(window) = handle.get_webview_window(MAIN_WINDOW) {
                    if ready {
                        if let Ok(url) = backend::studio_url().parse() {
                            let _ = window.navigate(url);
                        }
                    } else {
                        eprintln!(
                            "[shell] the studio engine did not answer within {} seconds",
                            READY_TIMEOUT.as_secs()
                        );
                    }
                    // Shown either way. A window carrying the splash message
                    // is better than an application that never appears and
                    // gives the user nothing to act on.
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // Close hides. The studio runs a scheduler, so the window closing
            // must not take the engine with it, and a creator who clicks the X
            // means "get this off my screen", not "stop posting".
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("failed to start the LinkedIn Studio shell")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(state) = app.try_state::<BackendState>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(instance) = guard.as_mut() {
                            instance.shutdown();
                        }
                    }
                }
            }
        });
}

/// What a check turned up, in the words the tray will show.
#[cfg(desktop)]
async fn run_update_check(app: &tauri::AppHandle) -> &'static str {
    use tauri_plugin_updater::UpdaterExt;

    let updater = match app.updater() {
        Ok(updater) => updater,
        // No endpoints or no public key. This build was made without them,
        // which is a fact about the build and not a failure the user caused.
        Err(error) => {
            eprintln!("[shell] updater unavailable: {}", error);
            return "Updates are not configured";
        }
    };

    match updater.check().await {
        Ok(Some(update)) => {
            // The signature is checked by the plugin against the public key
            // compiled into this build. An artifact that was not signed by the
            // matching private key is refused here, which is the entire reason
            // the keypair exists: without it, the update endpoint would be a
            // way to install arbitrary software on the user's machine.
            match update.download_and_install(|_, _| {}, || {}).await {
                Ok(()) => {
                    // Restarting is the install. Doing it without asking would
                    // take the window away mid sentence, so the user is told
                    // and chooses when, by quitting and reopening.
                    "Update installed. Restart to use it"
                }
                Err(error) => {
                    eprintln!("[shell] update download failed: {}", error);
                    "Update found, but it could not be installed"
                }
            }
        }
        Ok(None) => "You are on the latest version",
        Err(error) => {
            eprintln!("[shell] update check failed: {}", error);
            "Could not reach the update server"
        }
    }
}

/// Runs the check off the menu thread and reports back into the menu item.
///
/// The item's own label is the status surface. No dialog plugin, no
/// notification permission, and the answer appears exactly where the user
/// clicked to ask the question.
#[cfg(desktop)]
fn start_update_check(app: tauri::AppHandle, item: MenuItem<tauri::Wry>) {
    let _ = item.set_enabled(false);
    let _ = item.set_text("Checking for updates...");

    tauri::async_runtime::spawn(async move {
        let outcome = run_update_check(&app).await;
        let _ = item.set_text(outcome);
        let _ = item.set_enabled(true);
    });
}

fn build_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let open = MenuItem::with_id(app, "open", "Open Studio", true, None::<&str>)?;
    let update = MenuItem::with_id(app, "update", "Check for Updates", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &update, &quit])?;

    // Held so the async check can write its result back into the label.
    let update_item = update.clone();

    TrayIconBuilder::with_id("studio-tray")
        .icon(app.default_window_icon().unwrap().clone())
        .tooltip("LinkedIn Studio")
        .menu(&menu)
        // Left click opens, right click gets the menu. Showing the menu on
        // both makes the common action take two clicks.
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "open" => show_studio(app),
            #[cfg(desktop)]
            "update" => start_update_check(app.clone(), update_item.clone()),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_studio(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}
