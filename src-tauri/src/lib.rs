use serde::{Deserialize, Serialize};
use std::fs::{create_dir_all, OpenOptions};
use std::io::Write;
use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, RunEvent, State};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Clone, Serialize)]
struct RuntimeConfig {
    mode: &'static str,
    api_origin: String,
    token: String,
}

struct RuntimeState {
    config: RuntimeConfig,
    port: u16,
}
struct SidecarState(Mutex<Option<CommandChild>>);
struct JobState(Mutex<Option<isize>>);

const API_PROTOCOL_VERSION: u32 = 1;
const REQUIRED_CAPABILITIES: [&str; 3] = [
    "desktop-session-token",
    "selection-events",
    "system-diagnostics",
];

#[derive(Deserialize)]
struct HealthStatus {
    status: String,
    protocol_version: u32,
    capabilities: Vec<String>,
}

fn stockllm_data_dir() -> PathBuf {
    std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join("StockLLM")
}

fn launcher_log(message: &str) {
    let directory = stockllm_data_dir().join("logs");
    let _ = create_dir_all(&directory);
    if let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(directory.join("desktop-launcher.log"))
    {
        let timestamp_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_millis())
            .unwrap_or_default();
        let entry = serde_json::json!({
            "timestamp_unix_ms": timestamp_ms,
            "level": "error",
            "component": "desktop",
            "event": "launcher",
            "message": message,
        });
        let _ = writeln!(file, "{}", entry);
    }
}

fn random_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn runtime_config(state: State<'_, RuntimeState>) -> RuntimeConfig {
    state.config.clone()
}

#[tauri::command]
fn open_data_directory(app: AppHandle) -> Result<(), String> {
    let path = stockllm_data_dir();
    create_dir_all(&path).map_err(|error| error.to_string())?;
    app.opener()
        .open_path(path.to_string_lossy().into_owned(), None::<&str>)
        .map_err(|error| error.to_string())
}

fn stop_sidecar(app: &AppHandle) {
    if let Some(state) = app.try_state::<SidecarState>() {
        if let Ok(mut child) = state.0.lock() {
            if let Some(process) = child.take() {
                let _ = process.kill();
            }
        }
    }
    close_sidecar_job(app);
}

#[cfg(windows)]
fn close_sidecar_job(app: &AppHandle) {
    use windows_sys::Win32::Foundation::CloseHandle;

    if let Some(state) = app.try_state::<JobState>() {
        if let Ok(mut job) = state.0.lock() {
            if let Some(handle) = job.take() {
                unsafe { CloseHandle(handle as _) };
            }
        }
    }
}

#[cfg(not(windows))]
fn close_sidecar_job(_: &AppHandle) {}

#[cfg(windows)]
fn assign_sidecar_job(app: &AppHandle, pid: u32) -> Result<(), String> {
    use std::mem::{size_of, zeroed};
    use std::ptr::null;
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
    };

    unsafe {
        let job = CreateJobObjectW(null(), null());
        if job.is_null() || job == INVALID_HANDLE_VALUE {
            return Err("CreateJobObjectW failed".into());
        }
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as _,
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        ) == 0
        {
            CloseHandle(job);
            return Err("SetInformationJobObject failed".into());
        }
        let process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
        if process.is_null() || process == INVALID_HANDLE_VALUE {
            CloseHandle(job);
            return Err("OpenProcess failed".into());
        }
        let assigned = AssignProcessToJobObject(job, process);
        CloseHandle(process);
        if assigned == 0 {
            CloseHandle(job);
            return Err("AssignProcessToJobObject failed".into());
        }
        let state = app.state::<JobState>();
        let mut current = state.0.lock().map_err(|_| "Job state lock failed")?;
        if let Some(previous) = current.replace(job as isize) {
            CloseHandle(previous as _);
        }
    }
    Ok(())
}

#[cfg(not(windows))]
fn assign_sidecar_job(_: &AppHandle, _: u32) -> Result<(), String> {
    Ok(())
}

fn start_sidecar(app: &AppHandle, port: u16, token: &str) -> Result<(), String> {
    let command = app
        .shell()
        .sidecar("stockllm-backend")
        .map_err(|error| error.to_string())?
        .env("STOCKLLM_PACKAGED", "1")
        .env("STOCKLLM_PORT", port.to_string())
        .env("STOCKLLM_PARENT_PID", std::process::id().to_string())
        .env("STOCKLLM_DESKTOP_TOKEN", token);
    let (mut receiver, child) = command.spawn().map_err(|error| error.to_string())?;
    let pid = child.pid();
    if let Err(error) = assign_sidecar_job(app, pid) {
        launcher_log(&format!("Sidecar job protection unavailable: {error}"));
    }
    let state = app.state::<SidecarState>();
    let mut current = state.0.lock().map_err(|_| "Sidecar state lock failed")?;
    *current = Some(child);
    drop(current);
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Error(error) => launcher_log(&format!("Sidecar error: {error}")),
                CommandEvent::Terminated(status) => {
                    launcher_log(&format!("Sidecar terminated: {status:?}"))
                }
                _ => {}
            }
        }
    });
    Ok(())
}

fn validate_health(health: &HealthStatus) -> Result<(), String> {
    if health.status != "ok" {
        return Err(format!("Sidecar reported status {}", health.status));
    }
    if health.protocol_version != API_PROTOCOL_VERSION {
        return Err(format!(
            "Sidecar protocol mismatch: expected {}, received {}",
            API_PROTOCOL_VERSION, health.protocol_version
        ));
    }
    let missing: Vec<&str> = REQUIRED_CAPABILITIES
        .iter()
        .copied()
        .filter(|capability| !health.capabilities.iter().any(|value| value == capability))
        .collect();
    if !missing.is_empty() {
        return Err(format!(
            "Sidecar missing capabilities: {}",
            missing.join(", ")
        ));
    }
    Ok(())
}

#[tauri::command]
fn restart_backend(app: AppHandle, runtime: State<'_, RuntimeState>) -> Result<(), String> {
    stop_sidecar(&app);
    start_sidecar(&app, runtime.port, &runtime.config.token)
}

async fn reveal_when_ready(app: AppHandle, api_origin: String) {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build();
    let mut ready = false;
    let mut failure = "Sidecar health check timed out".to_string();
    if let Ok(client) = client {
        for _ in 0..60 {
            if let Ok(response) = client
                .get(format!("{api_origin}/api/v1/health"))
                .send()
                .await
            {
                if response.status().is_success() {
                    match response
                        .json::<HealthStatus>()
                        .await
                        .map_err(|error| format!("Invalid sidecar health response: {error}"))
                        .and_then(|health| validate_health(&health))
                    {
                        Ok(()) => {
                            ready = true;
                            break;
                        }
                        Err(error) => {
                            failure = error;
                            break;
                        }
                    }
                }
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
    }
    if ready {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
        }
    } else {
        launcher_log(&failure);
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

pub fn run() {
    let port = random_port().expect("failed to allocate loopback port");
    let token = uuid::Uuid::new_v4().simple().to_string();
    let api_origin = format!("http://127.0.0.1:{port}");
    let runtime = RuntimeConfig {
        mode: "desktop",
        api_origin: api_origin.clone(),
        token: token.clone(),
    };

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .manage(RuntimeState {
            config: runtime,
            port,
        })
        .manage(SidecarState(Mutex::new(None)))
        .manage(JobState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            runtime_config,
            open_data_directory,
            restart_backend
        ])
        .setup(move |app| {
            start_sidecar(app.handle(), port, &token).map_err(std::io::Error::other)?;
            let handle = app.handle().clone();
            let origin = api_origin.clone();
            tauri::async_runtime::spawn(reveal_when_ready(handle, origin));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build StockLLM desktop application");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            stop_sidecar(handle);
        }
    });
}
