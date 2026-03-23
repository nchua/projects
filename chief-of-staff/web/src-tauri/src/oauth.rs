use std::collections::HashMap;
use std::sync::Mutex;
use tauri::Emitter;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;
use tokio::sync::oneshot;

/// Global shutdown sender — dropping it cancels the previous listener.
static LISTENER_SHUTDOWN: Mutex<Option<oneshot::Sender<()>>> = Mutex::new(None);

/// Payload emitted to the webview when the OAuth callback arrives.
#[derive(Clone, serde::Serialize)]
struct OAuthCallbackPayload {
    code: String,
    state: String,
}

const SUCCESS_HTML: &str = r#"<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Authorization Complete</title>
<style>body{font-family:-apple-system,system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0a0a0a;color:#e5e5e5}
.card{text-align:center;padding:2rem}.check{font-size:2rem;margin-bottom:1rem;color:#22c55e}p{color:#999;font-size:0.875rem}</style>
</head>
<body><div class="card"><div class="check">&#10003;</div><h2>Authorization complete</h2><p>You can close this tab and return to Jarvis.</p></div></body>
</html>"#;

/// Fixed port for the OAuth callback listener.
/// Must match the redirect URI registered with OAuth providers.
const OAUTH_PORT: u16 = 19284;

/// Start a temporary localhost HTTP server that waits for an OAuth callback.
///
/// Returns the port number so the frontend can build `http://localhost:{port}/callback`
/// as the redirect_uri. After receiving one request with `code` + `state` query params,
/// it emits an `oauth-callback` Tauri event and shuts down.
#[tauri::command]
pub async fn start_oauth_listener(app: tauri::AppHandle) -> Result<u16, String> {
    // Cancel any previous listener so the port is freed
    if let Ok(mut guard) = LISTENER_SHUTDOWN.lock() {
        if let Some(tx) = guard.take() {
            let _ = tx.send(());
        }
    }

    // Brief pause to let the OS release the socket
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;

    let listener = TcpListener::bind(format!("127.0.0.1:{OAUTH_PORT}"))
        .await
        .map_err(|e| format!("Failed to bind listener on port {OAUTH_PORT}: {e}"))?;

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();
    if let Ok(mut guard) = LISTENER_SHUTDOWN.lock() {
        *guard = Some(shutdown_tx);
    }

    // Spawn a task that waits for exactly one connection, then shuts down.
    tauri::async_runtime::spawn(async move {
        let result = tokio::time::timeout(std::time::Duration::from_secs(300), async {
            tokio::select! {
                _ = shutdown_rx => {
                    // Previous listener cancelled — exit cleanly
                    Ok::<(), std::io::Error>(())
                }
                accept_result = listener.accept() => {
                    let (mut stream, _) = accept_result?;

                    // Read the HTTP request (up to 8KB is plenty for a callback URL)
                    let mut buf = vec![0u8; 8192];
                    let n = stream.read(&mut buf).await?;
                    let request = String::from_utf8_lossy(&buf[..n]);

                    // Parse query params from the GET request line
                    let (code, state) = parse_callback_params(&request);

                    // Send HTTP response to the browser
                    let body = SUCCESS_HTML;
                    let response = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    );
                    stream.write_all(response.as_bytes()).await?;
                    stream.flush().await?;

                    // Emit event to the webview
                    if let (Some(code), Some(state)) = (code, state) {
                        let _ = app.emit(
                            "oauth-callback",
                            OAuthCallbackPayload { code, state },
                        );
                    }

                    Ok(())
                }
            }
        })
        .await;

        match result {
            Ok(Ok(())) => {}
            Ok(Err(e)) => eprintln!("OAuth listener error: {e}"),
            Err(_) => eprintln!("OAuth listener timed out after 5 minutes"),
        }
    });

    Ok(OAUTH_PORT)
}

/// Extract `code` and `state` query parameters from an HTTP GET request line.
fn parse_callback_params(request: &str) -> (Option<String>, Option<String>) {
    // First line looks like: GET /callback?code=xxx&state=yyy HTTP/1.1
    let first_line = request.lines().next().unwrap_or("");
    let path = first_line.split_whitespace().nth(1).unwrap_or("");

    let query = match path.split_once('?') {
        Some((_, q)) => q,
        None => return (None, None),
    };

    let params: HashMap<&str, &str> = query
        .split('&')
        .filter_map(|pair| pair.split_once('='))
        .collect();

    (
        params.get("code").map(|s| s.to_string()),
        params.get("state").map(|s| s.to_string()),
    )
}
