//! Supervision of the Python backend.
//!
//! The shell does not implement any of the product. It starts the same uvicorn
//! process the .bat launcher starts, waits until that process is actually
//! answering, and stops it on the way out. Everything else is the backend's
//! job, which is what keeps the studio runnable without this shell at all.
//!
//! Two rules shape this file.
//!
//! The first is that the shell must never kill a server it did not start. A
//! creator may already have the studio running from the tray or the launcher,
//! with a scheduler mid post. Opening the desktop app then has to attach to
//! that server, and quitting the desktop app has to leave it running.
//!
//! The second is that "the port is open" is not "the backend is ready". A TCP
//! connect succeeds the moment uvicorn binds, which is before the database has
//! migrated. Showing the window then means showing a connection error to a
//! user who did nothing wrong, so readiness is read from the health endpoint
//! and the response is checked for this application's own name.
//!
//! Strict Invariants:
//! - Zero em-dashes.
//! - Never terminate a backend this process did not spawn.
//! - No HTTP dependency. A readiness probe is not worth a TLS stack.

use std::io::{Read, Write};
use std::net::{Shutdown, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::time::{Duration, Instant};

/// The port is fixed rather than chosen at runtime, because the browser
/// extension hardcodes it. A shell that moved the port would silently break
/// LinkedIn capture, which is the one thing this product cannot do without.
pub const STUDIO_PORT: u16 = 8000;
pub const STUDIO_HOST: &str = "127.0.0.1";

const PROBE_TIMEOUT: Duration = Duration::from_millis(600);

/// How the backend came to be running, which decides whether we may stop it.
pub enum Backend {
    /// This process started it. Ours to shut down.
    Spawned(Child),
    /// It was already serving. Someone else's, and left alone.
    Attached,
}

impl Backend {
    pub fn shutdown(&mut self) {
        match self {
            Backend::Spawned(child) => {
                // Best effort. A backend that already exited is the outcome we
                // wanted anyway.
                let _ = child.kill();
                let _ = child.wait();
            }
            Backend::Attached => {
                // Deliberately nothing. Another launcher owns this process and
                // may have a scheduler mid post.
            }
        }
    }
}

pub fn studio_url() -> String {
    format!("http://{}:{}", STUDIO_HOST, STUDIO_PORT)
}

/// Asks the health endpoint whether the studio is up, and whether it is ours.
///
/// A hand written request rather than an HTTP crate. The probe needs one
/// unauthenticated GET against loopback, and pulling in a full client with a
/// TLS stack to do it would add minutes to every build for no benefit.
///
/// The response body is checked for the application name, so a different
/// program holding port 8000 reads as "not ready" rather than as a studio the
/// shell can point a window at.
pub fn is_ready() -> bool {
    let address = format!("{}:{}", STUDIO_HOST, STUDIO_PORT);
    let stream = TcpStream::connect(&address);

    let mut stream = match stream {
        Ok(s) => s,
        Err(_) => return false,
    };

    let _ = stream.set_read_timeout(Some(PROBE_TIMEOUT));
    let _ = stream.set_write_timeout(Some(PROBE_TIMEOUT));

    let request = format!(
        "GET /api/v1/health HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\n\r\n",
        STUDIO_HOST, STUDIO_PORT
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut response = String::new();
    let mut buffer = [0u8; 2048];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => break,
            Ok(n) => {
                response.push_str(&String::from_utf8_lossy(&buffer[..n]));
                if response.len() > 8192 {
                    break;
                }
            }
            Err(_) => break,
        }
    }
    let _ = stream.shutdown(Shutdown::Both);

    response.starts_with("HTTP/1.1 200") && response.contains("inox-hydra")
}

/// Blocks until the backend answers, or the deadline passes.
pub fn wait_until_ready(timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if is_ready() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

/// Where the interpreter lives inside the installed bundle.
///
/// The layout mirrors what tools/build_portable.py produces, because the same
/// staged payload is what the installer carries:
///
///     <resources>/runtime/python.exe   the embeddable interpreter
///     <resources>/lib                  vendored dependencies
///     <resources>/app/studio           the application package
///
/// runtime/python3XX._pth puts ..\lib and ..\app on sys.path, so the
/// interpreter resolves its own imports and this code does not set PYTHONPATH.
pub fn interpreter_path(resources: &Path) -> PathBuf {
    resources.join("runtime").join("python.exe")
}

/// Starts uvicorn, or reports that someone already has.
pub fn start(resources: &Path) -> Result<Backend, String> {
    if is_ready() {
        return Ok(Backend::Attached);
    }

    let python = interpreter_path(resources);
    if !python.exists() {
        return Err(format!(
            "the bundled interpreter is missing at {}. The installer did not carry its payload.",
            python.display()
        ));
    }

    let mut command = Command::new(&python);
    command
        .arg("-m")
        .arg("uvicorn")
        .arg("studio.backend.app:app")
        .arg("--host")
        .arg(STUDIO_HOST)
        .arg("--port")
        .arg(STUDIO_PORT.to_string())
        .current_dir(resources);

    // No console window. Without this the user gets a black box flashing up
    // behind their application at every launch.
    //
    // The child's stdout and stderr are therefore discarded. A Python process
    // that dies on an import error looks identical to one still starting, and
    // the only signal is the readiness timeout. Piping the child's output to a
    // log file is the fix and is not done here.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    // spawn() succeeding means the process was created, not that it stayed
    // alive. Readiness is established by wait_until_ready, never by this.
    match command.spawn() {
        Ok(child) => Ok(Backend::Spawned(child)),
        Err(err) => Err(format!("could not start the studio engine: {}", err)),
    }
}
