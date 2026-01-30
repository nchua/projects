# Playground + Claude Integration

**Problem:** Users configure options in a playground, then have to leave and ask Claude about the implications of their choices. We want to bring that discussion INTO the playground.

**Solution:** Bidirectional communication where Claude can see the playground state AND send commands back to modify it.

## Live Demo

**[demo.html](demo.html)** - Full working demo with simulated Claude responses

Try it:
1. Open `demo.html` in your browser
2. Click "What are the trade-offs of my current config?"
3. Click the "Switch to Recommended" button in Claude's response
4. Watch the playground controls update automatically

## How It Works

```
┌─────────────────┐                    ┌─────────────────────┐
│   Claude Code   │ ←── WebSocket ───→ │   Browser (HTML)    │
│   (CLI)         │     Bridge         │   playground.html   │
│                 │                    │                     │
│  Receives:      │                    │  Sends: state JSON  │
│  - Questions    │                    │  Receives: commands │
│  - State JSON   │                    │                     │
│                 │                    │  Has:               │
│  Sends:         │                    │  - state object     │
│  - Answers      │                    │  - updateAll()      │
│  - Commands     │                    │  - command handler  │
└─────────────────┘                    └─────────────────────┘
```

### Key Insight

The playground already has the right architecture:

```javascript
const state = { /* all configurable values */ };

function updateAll() {
  renderPreview();
  renderPrompt();
}
```

Adding a command handler is straightforward:

```javascript
function handleClaudeCommand(cmd) {
  switch(cmd.action) {
    case 'setState':
      state[cmd.key] = cmd.value;
      updateAll();
      break;
    case 'applyPreset':
      applyPreset(cmd.preset);
      break;
  }
}
```

### Claude Response Format

Responses include both text AND actionable commands:

```json
{
  "text": "For a fitness app, biometric auth is overkill...",
  "actions": [
    {
      "label": "Apply recommended settings",
      "command": { "action": "applyPreset", "preset": "recommended" }
    }
  ]
}
```

## Design Explorations

| File | Approach | Description |
|------|----------|-------------|
| [mockup-modal.html](mockup-modal.html) | Modal Dialog | "Ask Claude" button opens focused question modal |
| [mockup-split-panel.html](mockup-split-panel.html) | Persistent Panel | Always-visible collapsible assistant on right side |
| [mockup-extensible.html](mockup-extensible.html) | Framework Demo | Shows how Claude adapts to different playground types |

## Implementation Path

### Phase 1: Clipboard (Works Now)
- "Copy context to Claude" button
- User pastes response back
- Manual but functional

### Phase 2: WebSocket Bridge
- Claude Code spawns bridge process on `open playground.html`
- Real-time bidirectional communication
- Bridge terminates when playground closes

### Phase 3: Native Integration
- `claude-code://` URL scheme for message passing
- Or embedded Claude web mode

## Technical Constraints

| Aspect | Difficulty | Notes |
|--------|------------|-------|
| Playground receiving commands | Easy | Just add message handler |
| Playground sending state | Easy | State is already JSON |
| Communication channel | Hard | Core unsolved problem |
| Claude understanding context | Easy | Structured data |
| Claude generating commands | Medium | Needs schema |

---

Built while exploring improvements to the [Claude Code playground skill](https://github.com/anthropics/claude-code).
