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
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

/// The port is fixed rather than chosen at runtime, because the browser
/// extension hardcodes it. A shell that moved the port would silently break
/// LinkedIn capture, which is the one thing this product cannot do without.
pub const STUDIO_PORT: u16 = 8000;
pub const STUDIO_HOST: &str = "127.0.0.1";

const PROBE_TIMEOUT: Duration = Duration::from_millis(600);

/// Bound on the engine log. It exists to explain the launch that just failed,
/// not to accumulate forever on a machine nobody maintains.
const MAX_LOG_BYTES: u64 = 2 * 1024 * 1024;

/// Where the engine's output is written.
///
/// Mirrors `_platform_user_data_dir` and `get_logs_dir` in
/// studio/backend/paths.py, including the INOX_HYDRA_HOME override, so the
/// file lands in the same directory the Python side uses. That is deliberate:
/// support.py's diagnostics bundle already tails the newest files there, so
/// the shell's log is collected with no further wiring.
fn engine_log_path() -> Option<PathBuf> {
    let home = match std::env::var("INOX_HYDRA_HOME") {
        Ok(value) if !value.trim().is_empty() => PathBuf::from(value),
        _ => PathBuf::from(std::env::var("LOCALAPPDATA").ok()?).join("InoxHydra"),
    };
    Some(home.join("logs").join("engine.log"))
}

/// Opens the engine log, appending, and marks the start of this launch.
///
/// Returns None on any failure. Logging is a diagnostic aid and never a
/// precondition for starting the product.
fn open_engine_log() -> Option<std::fs::File> {
    let path = engine_log_path()?;
    std::fs::create_dir_all(path.parent()?).ok()?;

    if let Ok(meta) = std::fs::metadata(&path) {
        if meta.len() > MAX_LOG_BYTES {
            let _ = std::fs::remove_file(&path);
        }
    }

    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .ok()?;

    // Seconds since the epoch rather than a formatted date, because rendering
    // a civil date needs a crate and this line only has to separate one launch
    // from the previous one. Every line after it comes from uvicorn, which
    // timestamps its own output.
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let _ = writeln!(file, "\n--- engine launch at unix time {} ---", stamp);

    Some(file)
}

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

/// Ties the engine's lifetime to this process, so a crash cannot orphan it.
///
/// `Backend::shutdown` covers the ordinary exit and is the path that respects
/// the attach rule. It does not run when the shell is killed outright: End
/// Task, an abort, a power event. The engine then keeps running with no window
/// of its own, holding port 8000. The next launch finds the port taken, and
/// because `is_ready` correctly reports that engine as healthy, the shell
/// attaches to a process the user cannot see and did not knowingly leave
/// behind.
///
/// A Job Object with KILL_ON_JOB_CLOSE makes Windows enforce it. When the last
/// handle to the job closes, every process in the job is terminated, and the
/// kernel closes our handle when this process dies however it dies. That is
/// the only mechanism that survives a kill we never get to respond to.
///
/// Declared by hand rather than adding the windows crate. This is four calls
/// and one struct whose layout has been fixed since Windows XP, weighed
/// against a dependency that would cost build time on every CI run from here
/// on. Every failure path below is non fatal and leaves exactly the previous
/// behaviour: an engine that outlives an abnormal exit, which is what we had.
#[cfg(windows)]
mod job_object {
    use std::ffi::c_void;
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    type Handle = *mut c_void;

    const KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;
    /// JOBOBJECTINFOCLASS::JobObjectExtendedLimitInformation
    const EXTENDED_LIMIT_INFORMATION: i32 = 9;

    #[repr(C)]
    #[derive(Default)]
    struct BasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: u32,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    #[derive(Default)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    #[derive(Default)]
    struct ExtendedLimitInformation {
        basic_limit_information: BasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateJobObjectW(security: *mut c_void, name: *const u16) -> Handle;
        fn SetInformationJobObject(
            job: Handle,
            class: i32,
            info: *const c_void,
            length: u32,
        ) -> i32;
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
        fn CloseHandle(object: Handle) -> i32;
    }

    pub fn tie_to_this_process(child: &Child) {
        unsafe {
            let job = CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
            if job.is_null() {
                return;
            }

            let mut limits = ExtendedLimitInformation::default();
            limits.basic_limit_information.limit_flags = KILL_ON_JOB_CLOSE;

            if SetInformationJobObject(
                job,
                EXTENDED_LIMIT_INFORMATION,
                &limits as *const ExtendedLimitInformation as *const c_void,
                std::mem::size_of::<ExtendedLimitInformation>() as u32,
            ) == 0
            {
                CloseHandle(job);
                return;
            }

            if AssignProcessToJobObject(job, child.as_raw_handle()) == 0 {
                CloseHandle(job);
                return;
            }

            // The handle is held for the life of this process on purpose, and
            // is never closed here. Closing it would close the job, and
            // kill-on-close would take the engine down immediately rather than
            // at our exit. The kernel closes it for us when we die, which is
            // precisely the moment the engine should follow.
        }
    }
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

    // Capture the child's output before it is thrown away.
    //
    // CREATE_NO_WINDOW below means there is no console for the child to write
    // to, so without this its stdout and stderr go nowhere at all. A Python
    // process that dies on an import error then looks exactly like one still
    // starting: the only signal is the readiness timeout, the user gets a
    // splash that never resolves, and there is nothing anywhere to inspect.
    // Release builds set the Windows subsystem, so the shell has no stderr of
    // its own to fall back on either.
    if let Some(file) = open_engine_log() {
        match file.try_clone() {
            Ok(errors) => {
                command.stdout(Stdio::from(file)).stderr(Stdio::from(errors));
            }
            // Only one handle. stderr takes it, because a traceback explains a
            // failed launch and an access log does not.
            Err(_) => {
                command.stderr(Stdio::from(file));
            }
        }
    }

    // No console window. Without this the user gets a black box flashing up
    // behind their application at every launch.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    // spawn() succeeding means the process was created, not that it stayed
    // alive. Readiness is established by wait_until_ready, never by this.
    match command.spawn() {
        Ok(child) => {
            // Only ever applied to a child we started. An attached backend
            // returns above and never reaches here, so the rule that the shell
            // must not kill a server it did not start holds: a job that killed
            // someone else's engine would break it in the worst possible way,
            // silently and at exit.
            #[cfg(windows)]
            job_object::tie_to_this_process(&child);

            Ok(Backend::Spawned(child))
        }
        Err(err) => Err(format!("could not start the studio engine: {}", err)),
    }
}
