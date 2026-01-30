# Playground + Claude Integration

**Problem:** Users configure options in a playground, then have to leave and ask Claude about the implications of their choices. We want to bring that discussion INTO the playground.

**Solution:** Bidirectional communication where Claude can see the playground state AND send commands back to modify it.

## Live Demo

**[demo.html](demo.html)** - Full working demo with real Claude API integration

Try it:
1. Open `demo.html` in your browser
2. Enter your Anthropic API key (from console.anthropic.com)
3. Ask any question - Claude sees your config and can modify it
4. Click action buttons in responses to apply changes

## Key Features

- **Real Claude API integration** - Not simulated, actual Claude responses
- **Bidirectional communication** - Claude reads state AND modifies it
- **Dynamic UI modification** - Claude can add/remove preset buttons
- **Collapsible panel** - Minimize Claude assistant when you need more space
- **Extensible architecture** - Easy to adapt for any playground type

## How It Works

```
┌─────────────────┐                    ┌─────────────────────┐
│  Claude API     │ ←── HTTP ────────→ │   Browser (HTML)    │
│                 │                    │   playground.html   │
│  Receives:      │                    │                     │
│  - State JSON   │                    │  Sends: state JSON  │
│  - Questions    │                    │  Receives: answers  │
│                 │                    │           + actions │
│  Sends:         │                    │                     │
│  - Answers      │                    │  Executes:          │
│  - ACTION cmds  │                    │  - applyPreset      │
│                 │                    │  - setState         │
│                 │                    │  - addPreset        │
│                 │                    │  - removePreset     │
└─────────────────┘                    └─────────────────────┘
```

## Extensibility: Adapting for Other Playgrounds

The demo uses a `PLAYGROUND_CONFIG` object that makes it easy to adapt for **any** playground type:

- Game Settings
- API Design
- Database Schema
- UI Components
- Technical Architecture
- Color Palettes
- And more...

### Configuration Structure

```javascript
const PLAYGROUND_CONFIG = {
    // Basic info
    name: 'Game Settings',
    description: 'Configure gameplay parameters',

    // What Claude should know about this domain
    domain: 'game design and balancing',
    expertRole: 'game designer helping balance gameplay mechanics',

    // Quick question suggestions
    quickQuestions: [
        { label: 'Too hard?', question: 'Is this too difficult for casual players?' },
        { label: 'Balanced?', question: 'Are these settings balanced?' }
    ],

    // Describe state keys so Claude knows what it can modify
    stateSchema: {
        difficulty: { type: 'enum', values: ['easy', 'medium', 'hard'] },
        enemySpeed: { type: 'number', min: 0.5, max: 3.0 },
        enablePowerups: { type: 'boolean' }
    },

    // How to generate context chips from current state
    getContextChips: (state) => [
        { label: 'Game Config', active: true },
        { label: state.difficulty + ' mode', active: true }
    ],

    // Describe presets for Claude
    presetDescriptions: {
        casual: 'Relaxed gameplay for new players',
        hardcore: 'For experienced players'
    }
};
```

### To Create a New Playground Type

1. Copy `demo.html`
2. Modify `PLAYGROUND_CONFIG` for your domain
3. Update `DEFAULTS` and `PRESETS` objects
4. Customize the control panel HTML
5. Update `renderPreview()` for your visualization

The Claude integration, action handling, and UI framework work automatically.

## Available Actions

Claude can include these action commands in responses:

| Action | Description | Example |
|--------|-------------|---------|
| `applyPreset` | Apply an existing preset | `{"action": "applyPreset", "preset": "recommended"}` |
| `setState` | Change a single setting | `{"action": "setState", "key": "difficulty", "value": "hard"}` |
| `addPreset` | Create a new preset button | `{"action": "addPreset", "name": "Custom", "id": "custom", "config": {...}}` |
| `removePreset` | Remove a preset button | `{"action": "removePreset", "id": "custom"}` |

## Design Mockups

| File | Approach | Description |
|------|----------|-------------|
| [mockup-modal.html](mockup-modal.html) | Modal Dialog | "Ask Claude" button opens focused question modal |
| [mockup-split-panel.html](mockup-split-panel.html) | Persistent Panel | Always-visible collapsible assistant on right side |
| [mockup-extensible.html](mockup-extensible.html) | Framework Demo | Shows how Claude adapts to different playground types |

## For Claude Code Native Integration

This demo calls the Anthropic API directly from the browser. For native Claude Code integration, the approach would be:

1. **Local endpoint** - Claude Code exposes a local HTTP server the HTML can POST to
2. **Or WebSocket bridge** - Spawned when opening the playground for real-time communication
3. **Or URL scheme** - `claude-code://` protocol for message passing

The HTML-side implementation is ready - it just needs a different endpoint URL.

---

Built while exploring improvements to the [Claude Code playground skill](https://github.com/anthropics/claude-code).
