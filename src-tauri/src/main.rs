// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::api::process::{Command, CommandEvent};
use std::sync::Mutex;
use tauri::Manager;

struct BackendState {
    child: Option<tauri::api::process::CommandChild>,
}

fn main() {
    tauri::Builder::default()
        .manage(Mutex::new(BackendState { child: None }))
        .setup(|app| {
            // 启动 Python 后端 sidecar
            let (mut rx, child) = Command::new_sidecar("backend")
                .expect("failed to create sidecar command")
                .spawn()
                .expect("failed to spawn sidecar");

            // 保存子进程引用
            let state = app.state::<Mutex<BackendState>>();
            state.lock().unwrap().child = Some(child);

            // 监听后端输出
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[Backend] {}", line);
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[Backend Error] {}", line);
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event.event() {
                // 关闭窗口时停止后端
                let child = {
                    let state = event.window().state::<Mutex<BackendState>>();
                    let mut guard = state.lock().unwrap();
                    guard.child.take()
                };
                if let Some(child) = child {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
