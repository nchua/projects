use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use serde::Deserialize;
use tauri::{
    image::Image,
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewUrl, WebviewWindowBuilder,
};
use tauri_plugin_notification::NotificationExt;

static TRAY_ICON_NORMAL: &[u8] = include_bytes!("../icons/tray-icon.png");
static TRAY_ICON_DOT: &[u8] = include_bytes!("../icons/tray-icon-dot.png");

#[derive(Debug, Deserialize)]
struct BriefingResponse {
    viewed_at: Option<String>,
    generated_at: Option<String>,
    content: Option<BriefingContent>,
}

#[derive(Debug, Deserialize)]
struct BriefingContent {
    action_items: Vec<serde_json::Value>,
    memory_context: Vec<serde_json::Value>,
}

pub fn create_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let icon = Image::from_bytes(TRAY_ICON_NORMAL)?;

    let _tray = TrayIconBuilder::with_id("jarvis-tray")
        .icon(icon)
        .icon_as_template(true)
        .tooltip("Jarvis")
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                position,
                ..
            } = event
            {
                let app = tray.app_handle();
                toggle_tray_popup(app, position);
            }
        })
        .build(app)?;

    // Start background polling
    let handle = app.handle().clone();
    tauri::async_runtime::spawn(poll_briefings(handle));

    Ok(())
}

fn toggle_tray_popup(app: &AppHandle, position: tauri::PhysicalPosition<f64>) {
    let x = position.x - 160.0;
    let y = position.y + 4.0;

    if let Some(window) = app.get_webview_window("tray-popup") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.set_position(tauri::Position::Physical(
                tauri::PhysicalPosition::new(x as i32, y as i32),
            ));
            let _ = window.show();
            let _ = window.set_focus();
        }
    } else {
        let url = WebviewUrl::App("/tray-popup".into());
        let _ = WebviewWindowBuilder::new(app, "tray-popup", url)
            .title("Jarvis Briefing")
            .inner_size(320.0, 400.0)
            .position(x, y)
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .resizable(false)
            .visible(true)
            .focused(true)
            .build();
    }
}

/// Background task that polls the briefing API, updates tray icon, and sends notifications.
async fn poll_briefings(app: AppHandle) {
    let api_url = std::env::var("NEXT_PUBLIC_API_URL")
        .unwrap_or_else(|_| "http://localhost:8000/api/v1".to_string());

    let client = reqwest::Client::new();
    let has_dot = Arc::new(AtomicBool::new(false));
    let notified_briefing = Arc::new(AtomicBool::new(false));
    let mut last_memory_count: Option<usize> = None;

    loop {
        tokio::time::sleep(Duration::from_secs(60)).await;

        let result = client
            .get(format!("{}/briefings/today", api_url))
            .send()
            .await;

        let briefing = match result {
            Ok(resp) if resp.status().is_success() => resp.json::<BriefingResponse>().await.ok(),
            _ => None,
        };

        if let Some(ref briefing) = briefing {
            let is_unviewed = briefing.generated_at.is_some() && briefing.viewed_at.is_none();

            // ── Tray icon dot ──
            let currently_dot = has_dot.load(Ordering::Relaxed);
            if is_unviewed != currently_dot {
                has_dot.store(is_unviewed, Ordering::Relaxed);
                if let Some(tray) = app.tray_by_id("jarvis-tray") {
                    let icon_bytes = if is_unviewed {
                        TRAY_ICON_DOT
                    } else {
                        TRAY_ICON_NORMAL
                    };
                    if let Ok(icon) = Image::from_bytes(icon_bytes) {
                        let _ = tray.set_icon(Some(icon));
                    }
                }
            }

            // ── Notification: morning briefing ready ──
            if is_unviewed && !notified_briefing.load(Ordering::Relaxed) {
                notified_briefing.store(true, Ordering::Relaxed);
                let action_count = briefing
                    .content
                    .as_ref()
                    .map(|c| c.action_items.len())
                    .unwrap_or(0);
                let body = format!(
                    "Morning briefing ready — {} priorities",
                    action_count,
                );
                let _ = app
                    .notification()
                    .builder()
                    .title("Jarvis")
                    .body(&body)
                    .show();
            }

            // Reset notification flag when briefing is viewed
            if !is_unviewed {
                notified_briefing.store(false, Ordering::Relaxed);
            }

            // ── Notification: new memory facts ──
            if let Some(ref content) = briefing.content {
                let current_count = content.memory_context.len();
                if let Some(prev) = last_memory_count {
                    if current_count > prev {
                        let new_facts = current_count - prev;
                        let body = format!(
                            "{} new context fact{} detected",
                            new_facts,
                            if new_facts == 1 { "" } else { "s" },
                        );
                        let _ = app
                            .notification()
                            .builder()
                            .title("Jarvis")
                            .body(&body)
                            .show();
                    }
                }
                last_memory_count = Some(current_count);
            }
        }
    }
}
