# Holocron — Product Spec v1.0

## Context

Nick has knowledge scattered across Gmail newsletters, Notion, his personal website/blog, and various files. Current tools require manual effort to create flashcards, connect concepts, and maintain a learning practice. Holocron consolidates this into one AI-powered learning system that builds itself from existing knowledge sources AND actively researches the web to stay current.

**First domains:** Applied AI (tools, workflows, staying current) + business strategy (from newsletters, web research, Notion notes)

**Vision:** Build for Nick first (single-user MVP), but architect for multi-user future. Obsidian support matters for future users even though Nick uses Notion today.

## Vision

**One sentence:** Holocron is the spaced repetition system that builds itself from your existing knowledge and uses AI to help you understand, not just memorize.

**Core loop:**
1. Subscribe to newsletters, take notes in Notion, bookmark things — live your life
2. Run `/holocron-refresh` in Claude Code (or scheduled cron) — AI reads Gmail newsletters, Notion pages, your blog, AND searches the web for new developments in your interest areas
3. Open the web app morning or evening for a 10-min review session
4. Over weeks, mastery grows and connections emerge across domains

**Positioning:** Holocron doesn't just process what you already have — it actively researches and brings you new knowledge. It's your AI learning partner, not just a card reviewer.

---

## Decisions from Interview

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary surface | **Web app** (Next.js) | Rich review UX, knowledge graph later |
| Infrastructure | **Separate project** | New repo, new Railway PostgreSQL, clean separation from fitness app |
| AI approach | **Hybrid: Claude Code now, API later** | Use Claude subscription via slash commands/MCP for MVP. Build API agent layer in Phase 2+ |
| Source ingestion | **MCP now, connectors later** | Gmail MCP + Notion MCP + WebSearch during Claude Code sessions. Proper connectors later |
| Web research | **Core capability** | On-demand deep dives + scheduled "what's new" sweeps across interest areas |
| Database | **New Railway PostgreSQL + pgvector** | Familiar infra, ~$5/mo, supports vector search |
| Card curation | **Trust but verify** | Auto-accept high-confidence cards, review uncertain ones |
| Organization | **Flat topics** | Simple: "AI Tools", "Business Strategy", "Swift". No nested hierarchy |
| Usage pattern | **Morning + evening sessions** | Dedicated 5-15 min focused review, not scattered throughout day |
| Knowledge graph | **Phase 3-4** | Focus on review engine + AI card generation first |
| Frontend | **Next.js (React)** | Claude Code builds it. Rich ecosystem for interactive review UX |
| Multi-user | **Build for Nick first** | Single-user MVP, but proper auth + data isolation for easy expansion |
| Notion | **Both notes + databases** | Freeform pages and structured databases as knowledge sources |
| Personal website | **Blog posts as source** | Nick's own writing contains insights worth retaining |

---

## Core Features

### 1. Spaced Repetition Engine (FSRS)

**Algorithm:** FSRS (Free Spaced Repetition Scheduler). Three-component memory model (stability, difficulty, retrievability). Parameters fit per user from review history.

**Key behaviors:**
- AI-generated cards start with 15-20% shorter intervals (no user generation effect), converge after first successful recall
- Default 90% retention target, adjustable per topic
- When prerequisite concepts weaken, dependent concepts get priority boost
- **Never punish missed days** — cap daily reviews (default 30), spread overdue items across days

**Rating:** 4 buttons (Forgot / Struggled / Got it / Easy) + implicit signals (hesitation time, time reading answer).

### 2. Learning Unit Types (MVP → Full)

**MVP (Phase 1-2):**
- **Concept Card** — term/definition, basic retrieval
- **Cloze-in-Context** — blanked terms in full paragraph

**Phase 3:**
- **Explanation Card** — Feynman-style "explain in your own words"
- **Application Problem** — apply concept to a novel scenario
- **Connection Card** — AI-discovered link between two concepts across domains
- **Generative Card** — user produces an example or analogy

### 3. AI Agent System (Hybrid Architecture)

**Phase 1 (Claude Code slash commands):**

```
/holocron-refresh
├── 1. Gmail MCP: Search newsletters by sender/label since last refresh
├── 2. Notion MCP: Check for new/updated pages in watched databases
├── 3. WebSearch: Search the web for new developments in configured interest areas
│   └── e.g., "latest AI agent frameworks", "business strategy trends March 2026"
├── 4. WebFetch: Read Nick's blog for new posts since last check
├── 5. Extract key concepts and insights from ALL sources
├── 6. Generate cards (Concept + Cloze types)
├── 7. POST cards to FastAPI (high-confidence → auto-accept, low → inbox)
└── 8. Report: "Generated 18 cards from 3 newsletters, 2 Notion pages, 4 web articles. 6 need review."
```

```
/holocron-research "How do AI agents handle tool use?"
├── WebSearch: Deep dive on the topic (multiple queries)
├── WebFetch: Read top articles, papers, blog posts
├── Synthesize findings into structured knowledge
├── Generate 10-15 cards across multiple types
├── POST to FastAPI with topic assignment
└── Report: "Created learning path: 'AI Agent Tool Use' with 12 cards across 5 concepts."
```

Both run as Claude Code skills. No API cost — uses your Claude subscription. `/holocron-refresh` can be scheduled via Claude Code cron (e.g., weekly Sunday evening). `/holocron-research` is on-demand.

**Phase 2+ (API-based agents):**
- Card Generator agent (Claude API, runs on source ingestion)
- Review Coach agent (evaluates open-ended answers during sessions)
- Connection Finder agent (scheduled, discovers cross-domain links)
- Web Monitor agent (scheduled, checks configured sources for new content)
- Research Agent (user-initiated via web app, deep dives without needing Claude Code)

### 4. Data Source Connectors

**MVP (via Claude Code MCP + tools):**
| Source | Method | What's Indexed |
|--------|--------|---------------|
| **Gmail newsletters** | Gmail MCP | Newsletter content filtered by sender/label |
| **Notion** | Notion MCP | Pages and database entries from watched workspaces |
| **Web research** | WebSearch + WebFetch | New articles, blog posts, papers on configured interest areas |
| **Personal blog** | WebFetch (URL check) | Nick's own blog posts for retention |
| **Manual input** | Web app form | User-written concepts and notes |

**Phase 2-3 (proper connectors, no Claude Code needed):**
| Source | Method | What's Indexed |
|--------|--------|---------------|
| **Gmail** | Gmail API | Newsletter content (replaces MCP) |
| **Notion** | Notion API | Pages + databases (replaces MCP) |
| **Obsidian vault** | Filesystem watcher (`watchdog`) | Markdown files, wikilinks, tags (for future users) |
| **RSS feeds** | Feed parser | Blog/newsletter feeds |

**Phase 4-5:**
| Source | Method | What's Indexed |
|--------|--------|---------------|
| **Google Drive** | `changes.list` API | Docs, Sheets |
| **Browser extension** | Chrome extension | Articles tagged "learn" |
| **Readwise** | API sync | Highlights and annotations |

**Ingestion flow:** New content → AI generates cards → high-confidence cards auto-accepted → uncertain cards go to Inbox for review.

### 5. Knowledge Graph (Phase 3-4)

Property graph in PostgreSQL. Concepts as nodes, four edge types:
- `PREREQUISITE` — hard gate
- `SUPPORTS` — soft priority boost
- `RELATES_TO` — connection cards
- `PART_OF` — hierarchy

Auto-constructed by AI during card generation. User can manually adjust.

### 6. Anti-Guilt Design

- **No streaks.** Mastery-based progress bars instead (30% → 80% over weeks).
- **No punishment for missed days.** Overdue items spread across coming days, not front-loaded.
- **Welcome back messaging.** "Let's pick up where you left off" not "247 overdue cards."
- **Capped daily reviews.** User-configurable (default 30). Sessions end on "I could do more."
- **Achievements tied to understanding**, not activity volume.

---

## Architecture

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js (React), deployed on Vercel |
| **API** | FastAPI (Python), deployed on Railway |
| **Database** | PostgreSQL + pgvector on Railway |
| **AI (MVP)** | Claude Code slash commands + Gmail MCP |
| **AI (later)** | Claude API with tool use |
| **Auth** | JWT (NextAuth.js on frontend, FastAPI on backend) |

### System Diagram

```
MVP Architecture:

  ┌──────────────┐         ┌──────────────────┐
  │  Next.js     │ ──API──▶│    FastAPI        │
  │  (Vercel)    │◀────────│    (Railway)      │
  └──────────────┘         └────────┬─────────┘
                                    │
                           ┌────────▼─────────┐
                           │   PostgreSQL     │
                           │   + pgvector     │
                           │   (Railway)      │
                           └──────────────────┘

  ┌──────────────────────────────────────────┐
  │  Claude Code (local, your subscription) │
  │                                          │
  │  /holocron-refresh                       │
  │  ├── Gmail MCP → read newsletters        │
  │  ├── Generate cards (Claude)             │
  │  └── POST cards to FastAPI               │
  └──────────────────────────────────────────┘
```

### Data Model

```sql
-- Core entities
topics (id, name, description, target_retention, created_at)
concepts (id, topic_id, name, description, mastery_score, tier, created_at)
concept_relationships (id, source_concept_id, target_concept_id, edge_type)

-- Learning content
learning_units (
  id, concept_id, type, -- 'concept', 'cloze', 'explanation', 'application', 'connection', 'generative'
  front_content, back_content,
  difficulty, stability, retrievability,
  source_id, -- provenance
  auto_accepted, -- trust-but-verify flag
  created_at
)

-- Review tracking
reviews (
  id, learning_unit_id,
  rating, -- 'forgot', 'struggled', 'got_it', 'easy'
  time_to_reveal_ms, time_reading_ms,
  reviewed_at
)

-- Sources
sources (id, type, uri, name, last_synced_at, created_at)
source_documents (id, source_id, content, chunk_index, embedding vector(1536), created_at)

-- Inbox
inbox_items (id, learning_unit_id, confidence_score, status, created_at)
  -- status: 'pending', 'accepted', 'rejected'

-- Agent tracking
agent_runs (id, agent_type, source_id, units_generated, tokens_used, cost, started_at, completed_at)
```

---

## UX Flows

### Daily Review Session (Web App)

**Landing state:**
```
┌─────────────────────────────────────────────┐
│  HOLOCRON                                   │
│                                             │
│  Good morning. 18 items due today.          │
│  Estimated time: ~10 min                    │
│                                             │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Quick 5 │  │ Full     │  │ Deep dive │  │
│  │ 5 min   │  │ 10 min   │  │ 20 min    │  │
│  └─────────┘  └──────────┘  └───────────┘  │
│                                             │
│  Topics today:                              │
│  ● AI Tools (8 due)                         │
│  ● Business Strategy (10 due)               │
│                                             │
│  Inbox: 5 cards awaiting review             │
└─────────────────────────────────────────────┘
```

**Card review (Concept type):**
```
┌─────────────────────────────────────────────┐
│  RECALL · AI Tools                          │
│                                             │
│  What is "chain of thought prompting" and   │
│  why does it improve LLM performance?       │
│                                             │
│           [ Show Answer ]                   │
│                                             │
│  Source: The Batch newsletter, Mar 12       │
└─────────────────────────────────────────────┘

          ▼ after reveal ▼

┌─────────────────────────────────────────────┐
│  CoT prompting breaks complex reasoning     │
│  into intermediate steps. It works because  │
│  it forces the model to show its work,      │
│  allocating more compute to each step and   │
│  reducing compounding errors.               │
│                                             │
│  [Forgot] [Struggled] [Got it] [Easy]       │
└─────────────────────────────────────────────┘
```

**Post-session:**
```
┌─────────────────────────────────────────────┐
│  SESSION COMPLETE · 10 min 23 sec           │
│                                             │
│  ● 15 recalled successfully                 │
│  ◐ 2 needed effort                          │
│  ○ 1 forgotten (rescheduled tomorrow)       │
│                                             │
│  Strongest: Business Strategy (100%)        │
│  Focus: AI agent architectures (struggled)  │
│                                             │
│  [ Done ]  [ Review inbox (5 items) ]       │
└─────────────────────────────────────────────┘
```

### Inbox Curation (Trust but Verify)
```
┌─────────────────────────────────────────────┐
│  INBOX · 5 pending                          │
│                                             │
│  From: Lenny's Newsletter (Mar 18)          │
│  Confidence: 94% ✓ auto-accepted            │
│                                             │
│  From: Stratechery (Mar 15)                 │
│  Confidence: 67% — needs review             │
│  ┌─────────────────────────────────────┐    │
│  │ Q: What is Stratechery's "Aggregation│   │
│  │    Theory" and how does it apply to  │    │
│  │    AI platforms?                     │    │
│  │ A: Aggregation Theory states that... │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  [ Accept ] [ Edit ] [ Reject ] [ Skip ]    │
└─────────────────────────────────────────────┘
```

### Mastery Dashboard
```
┌─────────────────────────────────────────────┐
│  YOUR MASTERY                               │
│                                             │
│  AI Tools            ████████░░  78%  ↑3%   │
│  Business Strategy   ██████░░░░  62%  ↑7%   │
│  Prompt Engineering  ████░░░░░░  41%  ↑1%   │
│                                             │
│  Total concepts: 84  │  Cards: 203          │
│  Mastered: 32        │  Learning: 52        │
│                                             │
│  This week: +6% avg mastery                 │
│  Last refresh: 2 days ago (12 cards added)  │
└─────────────────────────────────────────────┘
```

---

## Claude Code Integration

### `/holocron-refresh` Skill (MVP's killer feature)

A Claude Code slash command that pulls from ALL configured sources in one run:

1. **Gmail MCP** — search newsletters by sender/label since last refresh, read and extract insights
2. **Notion MCP** — check watched databases/pages for new or updated content
3. **WebSearch** — search configured interest areas for new developments (e.g., "AI agent frameworks 2026", "business strategy trends")
4. **WebFetch** — check Nick's blog and any monitored URLs for new posts
5. **Generate cards** — Concept Cards + Cloze-in-Context from all extracted knowledge
6. **Score confidence** — high-confidence → auto-accepted, low → inbox
7. **POST to FastAPI** — cards written to database
8. **Report** — summary of what was found and generated

**Scheduled via Claude Code cron** (e.g., every Sunday at 6 PM) or run manually.

### `/holocron-research` Skill

On-demand deep dive into any topic:
```
/holocron-research "How do AI agents handle tool use and when should you use function calling vs. code execution?"
```
- Runs multiple web searches, reads top articles
- Synthesizes into structured concepts
- Generates 10-15 cards across multiple types
- Creates a mini learning path

---

## MVP Phasing

### Phase 1: Foundation (Week 1-2)
- [ ] New repo + project setup
- [ ] Railway PostgreSQL with pgvector
- [ ] FastAPI backend: auth, topics, concepts, learning_units, reviews CRUD
- [ ] FSRS scheduler implementation (Python port of `py-fsrs`)
- [ ] Seed with manually created cards for testing
- [ ] Basic API tests

### Phase 2: Web App + AI Ingestion (Week 3-4)
- [ ] Next.js app: review session UI (Concept + Cloze cards)
- [ ] Rating flow (4 buttons + timing signals)
- [ ] `/holocron-refresh` Claude Code skill:
  - Gmail MCP (newsletters)
  - Notion MCP (pages + databases)
  - WebSearch + WebFetch (web research + blog monitoring)
  - Card generation + POST to API
- [ ] `/holocron-research` Claude Code skill (on-demand deep dives)
- [ ] Inbox curation UI (trust-but-verify)
- [ ] Session modes (Quick 5 / Full)
- [ ] Basic mastery dashboard

### Phase 3: More Card Types + Polish (Week 5-6)
- [ ] Explanation, Application, Connection, Generative card types
- [ ] Interleaving algorithm
- [ ] Anti-guilt features (overdue spreading, daily caps)
- [ ] Session pacing (warm-up → core → challenge → cool-down)
- [ ] Post-session summary
- [ ] `/holocron-refresh` cron scheduling (weekly auto-refresh)

### Phase 4: Knowledge Graph + Paths (Week 7-8)
- [ ] Concept relationships + graph queries
- [ ] Knowledge Map visualization (interactive graph)
- [ ] Learning Paths (AI-generated, adaptive)
- [ ] Connection Finder agent (Claude API)
- [ ] Multi-user auth + data isolation

### Phase 5: Standalone Connectors + Scale (Week 9+)
- [ ] Gmail API connector (replace MCP dependency)
- [ ] Notion API connector (replace MCP dependency)
- [ ] Obsidian vault connector (filesystem watcher — for future users)
- [ ] Review Coach agent (answer evaluation for open-ended cards)
- [ ] Google Drive connector
- [ ] Weekly insight reports
- [ ] PWA for mobile review sessions

---

## Verification Plan

### Phase 1 Testing
1. Create topics and concepts via API
2. Generate FSRS schedule, verify interval calculations
3. Submit reviews, verify retrievability updates
4. Confirm pgvector embeddings store and query correctly

### Phase 2 Testing
1. Run `/holocron-refresh` — verify Gmail newsletters are read and cards generated
2. Complete a full review session in the web app
3. Verify inbox shows low-confidence cards for curation
4. Check mastery scores update after reviews

### End-to-End Flow
1. Subscribe to a new newsletter → wait for next refresh
2. Cards appear in inbox → curate
3. Cards enter rotation → review over 3 sessions
4. Mastery dashboard reflects progress
5. FSRS intervals adjust based on performance

---

## Key Files to Create

```
holocron/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── core/          # Config, DB, FSRS engine
│   │   ├── models/        # SQLAlchemy models
│   │   └── schemas/       # Pydantic schemas
│   ├── alembic/           # Migrations
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── app/               # Next.js app router
│   ├── components/        # React components
│   └── package.json
├── skills/
│   └── holocron-refresh/  # Claude Code skill
├── CLAUDE.md
└── README.md
```
