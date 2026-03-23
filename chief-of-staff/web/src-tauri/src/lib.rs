mod oauth;
mod tray;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_global_shortcut::{
    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,
};

pub fn run() {
    let spotlight_shortcut = Shortcut::new(Some(Modifiers::META), Code::KeyJ);

    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &spotlight_shortcut
                        && event.state() == ShortcutState::Pressed
                    {
                        toggle_spotlight(app);
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .setup(move |app| {
            // Register the global shortcut
            app.global_shortcut().register(spotlight_shortcut)?;

            // Create system tray
            tray::create_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![oauth::start_oauth_listener])
        .run(tauri::generate_context!())
        .expect("error while running Jarvis");
}

fn toggle_spotlight(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("spotlight") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.center();
            let _ = window.show();
            let _ = window.set_focus();
        }
    } else {
        let url = WebviewUrl::App("/spotlight".into());
        let _ = WebviewWindowBuilder::new(app, "spotlight", url)
            .title("Jarvis Search")
            .inner_size(680.0, 420.0)
            .center()
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .resizable(false)
            .visible(true)
            .focused(true)
            .build();
    }
}
