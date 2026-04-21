// Shared fake dataset for mind-map mockups.
// 30 notes across ~6 topic clusters, with concept tags, source metadata,
// quotes, dates, and explicit cross-links so all three views render the
// same underlying knowledge graph.
//
// Schema:
//   notes:    [{ id, title, source_type, source_url, date_read, wpm, rpe,
//                topic, concepts:[id], quotes:[str], summary }]
//   concepts: [{ id, label, topic }]
//   topics:   [{ id, label, color }]
//
// Edges between concepts are derived at render time from concept
// co-occurrence within the same note.

window.MINDMAP_DATA = (function () {
  const topics = [
    { id: "t_learn",   label: "Learning Science", color: "#7aa2ff" },
    { id: "t_ai",      label: "AI / LLMs",        color: "#b48cff" },
    { id: "t_focus",   label: "Attention & Focus",color: "#ffb86b" },
    { id: "t_systems", label: "Systems Thinking", color: "#5fd6a4" },
    { id: "t_writing", label: "Writing & Notes",  color: "#ff7a90" },
    { id: "t_health",  label: "Sleep & Recovery", color: "#ffd86b" },
  ];

  const concepts = [
    // learning science
    { id: "c_recall",       label: "Active Recall",          topic: "t_learn" },
    { id: "c_spacing",      label: "Spaced Repetition",      topic: "t_learn" },
    { id: "c_interleave",   label: "Interleaving",           topic: "t_learn" },
    { id: "c_desirable",    label: "Desirable Difficulty",   topic: "t_learn" },
    { id: "c_metacog",      label: "Metacognition",          topic: "t_learn" },
    // ai
    { id: "c_llm",          label: "LLMs",                   topic: "t_ai" },
    { id: "c_rag",          label: "RAG",                    topic: "t_ai" },
    { id: "c_embed",        label: "Embeddings",             topic: "t_ai" },
    { id: "c_agent",        label: "Agents",                 topic: "t_ai" },
    { id: "c_eval",         label: "Evals",                  topic: "t_ai" },
    // focus
    { id: "c_deepwork",     label: "Deep Work",              topic: "t_focus" },
    { id: "c_attn_residue", label: "Attention Residue",      topic: "t_focus" },
    { id: "c_flow",         label: "Flow",                   topic: "t_focus" },
    // systems
    { id: "c_feedback",     label: "Feedback Loops",         topic: "t_systems" },
    { id: "c_leverage",     label: "Leverage Points",        topic: "t_systems" },
    { id: "c_secondorder",  label: "Second-Order Effects",   topic: "t_systems" },
    // writing
    { id: "c_zettel",       label: "Zettelkasten",           topic: "t_writing" },
    { id: "c_atomic",       label: "Atomic Notes",           topic: "t_writing" },
    { id: "c_evergreen",    label: "Evergreen Notes",        topic: "t_writing" },
    // health
    { id: "c_sleep",        label: "Sleep Architecture",     topic: "t_health" },
    { id: "c_hrv",          label: "HRV",                    topic: "t_health" },
    { id: "c_circadian",    label: "Circadian Rhythm",       topic: "t_health" },
  ];

  // Helper for dates over the last ~10 weeks.
  const D = (daysAgo) => {
    const d = new Date();
    d.setDate(d.getDate() - daysAgo);
    return d.toISOString().slice(0, 10);
  };

  const notes = [
    { id: "n01", title: "Make It Stick — ch. 2",          source_type: "book",       source_url: "",                         date_read: D(68), wpm: 420, rpe: 7, topic: "t_learn",
      concepts: ["c_recall","c_desirable","c_spacing"],
      quotes: ["Retrieval is learning.", "Easy practice is largely a waste."],
      summary: "Retrieval practice (testing) outperforms re-reading; difficulty during practice increases retention." },
    { id: "n02", title: "How spaced repetition works",     source_type: "article",    source_url: "https://example.com/srs",   date_read: D(64), wpm: 480, rpe: 6, topic: "t_learn",
      concepts: ["c_spacing","c_recall","c_metacog"],
      quotes: ["The forgetting curve is exponential."],
      summary: "Reviews scheduled at expanding intervals exploit the spacing effect; metacognitive accuracy matters." },
    { id: "n03", title: "Interleaving in motor learning",  source_type: "paper",      source_url: "",                         date_read: D(60), wpm: 360, rpe: 8, topic: "t_learn",
      concepts: ["c_interleave","c_desirable"],
      quotes: ["Blocked practice flatters performance, not learning."],
      summary: "Mixing problem types slows in-session gains but improves transfer." },
    { id: "n04", title: "Metacognition predicts study time",source_type: "paper",     source_url: "",                         date_read: D(57), wpm: 400, rpe: 7, topic: "t_learn",
      concepts: ["c_metacog","c_recall"],
      quotes: ["Students stop studying when they feel they know it — usually too soon."],
      summary: "Judgments of learning are systematically overconfident; testing recalibrates them." },

    { id: "n05", title: "Anthropic — building agents",     source_type: "article",    source_url: "https://example.com/agents", date_read: D(54), wpm: 500, rpe: 6, topic: "t_ai",
      concepts: ["c_agent","c_llm","c_eval"],
      quotes: ["Tools, not chains."],
      summary: "Prefer tool-using single agents over rigid prompt chains; evaluate end-to-end." },
    { id: "n06", title: "RAG patterns 2026",               source_type: "article",    source_url: "https://example.com/rag",    date_read: D(52), wpm: 460, rpe: 7, topic: "t_ai",
      concepts: ["c_rag","c_embed","c_eval"],
      quotes: ["Retrieval quality dominates generation quality."],
      summary: "Embedding choice + reranking matter more than the LLM for grounded QA." },
    { id: "n07", title: "Why most evals lie",              source_type: "blog",       source_url: "",                         date_read: D(49), wpm: 440, rpe: 8, topic: "t_ai",
      concepts: ["c_eval","c_llm"],
      quotes: ["If your eval doesn't predict prod, it's vibes."],
      summary: "Offline benchmarks rarely match user-facing quality; build task-specific evals." },
    { id: "n08", title: "Embeddings for personal notes",   source_type: "article",    source_url: "",                         date_read: D(46), wpm: 470, rpe: 6, topic: "t_ai",
      concepts: ["c_embed","c_rag"],
      quotes: ["MiniLM at 384 dims is enough for ~10k notes."],
      summary: "Local embedding models are sufficient for personal-scale knowledge graphs." },
    { id: "n09", title: "Agents that learn from feedback", source_type: "paper",      source_url: "",                         date_read: D(43), wpm: 410, rpe: 8, topic: "t_ai",
      concepts: ["c_agent","c_feedback","c_eval"],
      quotes: ["Closed-loop > open-loop."],
      summary: "Agents improve when their environment provides verifiable feedback." },

    { id: "n10", title: "Deep Work — opening chapter",     source_type: "book",       source_url: "",                         date_read: D(72), wpm: 380, rpe: 6, topic: "t_focus",
      concepts: ["c_deepwork","c_flow","c_attn_residue"],
      quotes: ["The ability to focus is becoming rare and therefore valuable."],
      summary: "Deliberate, distraction-free work is the leverage skill of the knowledge era." },
    { id: "n11", title: "Attention residue (Leroy)",       source_type: "paper",      source_url: "",                         date_read: D(40), wpm: 340, rpe: 9, topic: "t_focus",
      concepts: ["c_attn_residue","c_deepwork"],
      quotes: ["Switching tasks leaves cognitive sediment."],
      summary: "Even brief task switches degrade subsequent performance for ~20 minutes." },
    { id: "n12", title: "Flow state preconditions",        source_type: "article",    source_url: "",                         date_read: D(36), wpm: 420, rpe: 6, topic: "t_focus",
      concepts: ["c_flow","c_deepwork","c_desirable"],
      quotes: ["Skill matched to challenge."],
      summary: "Flow requires clear goals, immediate feedback, and challenge ≈ skill." },

    { id: "n13", title: "Thinking in Systems — intro",     source_type: "book",       source_url: "",                         date_read: D(75), wpm: 360, rpe: 7, topic: "t_systems",
      concepts: ["c_feedback","c_leverage","c_secondorder"],
      quotes: ["A system is more than the sum of its parts."],
      summary: "Stocks, flows, and feedback loops as the primitives of complex systems." },
    { id: "n14", title: "Leverage points (Meadows)",       source_type: "essay",      source_url: "",                         date_read: D(33), wpm: 320, rpe: 9, topic: "t_systems",
      concepts: ["c_leverage","c_feedback"],
      quotes: ["The most powerful intervention is to change the paradigm."],
      summary: "Twelve places to intervene in a system, ranked by leverage." },
    { id: "n15", title: "Second-order thinking in product", source_type: "blog",      source_url: "",                         date_read: D(28), wpm: 460, rpe: 6, topic: "t_systems",
      concepts: ["c_secondorder","c_feedback"],
      quotes: ["And then what?"],
      summary: "Predicting downstream effects of decisions beats reacting to first-order outcomes." },

    { id: "n16", title: "Zettelkasten primer",             source_type: "article",    source_url: "",                         date_read: D(70), wpm: 400, rpe: 6, topic: "t_writing",
      concepts: ["c_zettel","c_atomic","c_evergreen"],
      quotes: ["One idea per note."],
      summary: "Atomic, linked notes beat hierarchical folders for thinking." },
    { id: "n17", title: "Evergreen notes (Matuschak)",     source_type: "essay",      source_url: "",                         date_read: D(25), wpm: 380, rpe: 7, topic: "t_writing",
      concepts: ["c_evergreen","c_atomic","c_zettel"],
      quotes: ["Notes should be densely linked."],
      summary: "Evergreen notes accumulate value through revision and linking." },
    { id: "n18", title: "Atomic notes vs. literature notes", source_type: "blog",     source_url: "",                         date_read: D(22), wpm: 440, rpe: 6, topic: "t_writing",
      concepts: ["c_atomic","c_zettel"],
      quotes: ["Capture is not synthesis."],
      summary: "Literature notes are raw input; atomic notes are processed thought." },

    { id: "n19", title: "Walker — Why We Sleep ch. 3",     source_type: "book",       source_url: "",                         date_read: D(80), wpm: 400, rpe: 7, topic: "t_health",
      concepts: ["c_sleep","c_circadian"],
      quotes: ["Sleep is not the absence of wakefulness."],
      summary: "Sleep stages serve distinct memory consolidation roles." },
    { id: "n20", title: "HRV as a recovery proxy",         source_type: "article",    source_url: "",                         date_read: D(20), wpm: 460, rpe: 5, topic: "t_health",
      concepts: ["c_hrv","c_sleep"],
      quotes: ["Trends, not single readings."],
      summary: "HRV trend (not absolute) reflects autonomic recovery." },
    { id: "n21", title: "Circadian timing & cognition",    source_type: "paper",      source_url: "",                         date_read: D(16), wpm: 380, rpe: 8, topic: "t_health",
      concepts: ["c_circadian","c_sleep","c_deepwork"],
      quotes: ["Cognitive peak ≈ 2–4 hours after waking."],
      summary: "Difficult cognitive work is best done in the morning peak window." },

    // cross-cluster bridge notes
    { id: "n22", title: "Speed reading + retention",       source_type: "blog",       source_url: "",                         date_read: D(14), wpm: 600, rpe: 8, topic: "t_learn",
      concepts: ["c_recall","c_metacog","c_attn_residue"],
      quotes: ["Speed without recall is entertainment."],
      summary: "RSVP increases throughput but requires post-read recall to retain." },
    { id: "n23", title: "Using LLMs as study partners",    source_type: "article",    source_url: "",                         date_read: D(12), wpm: 480, rpe: 6, topic: "t_ai",
      concepts: ["c_llm","c_recall","c_metacog"],
      quotes: ["Quiz me, don't summarize for me."],
      summary: "LLMs are most useful for active recall prompts, not passive summaries." },
    { id: "n24", title: "Agents for personal knowledge",   source_type: "blog",       source_url: "",                         date_read: D(10), wpm: 500, rpe: 7, topic: "t_ai",
      concepts: ["c_agent","c_zettel","c_evergreen"],
      quotes: ["Your second brain should write back."],
      summary: "Agents that maintain a personal knowledge graph as you read." },
    { id: "n25", title: "Feedback loops in learning",      source_type: "essay",      source_url: "",                         date_read: D(8),  wpm: 420, rpe: 7, topic: "t_systems",
      concepts: ["c_feedback","c_recall","c_spacing"],
      quotes: ["Tight loops compound."],
      summary: "Spaced repetition is a feedback loop on memory itself." },
    { id: "n26", title: "Sleep and memory consolidation",  source_type: "paper",      source_url: "",                         date_read: D(6),  wpm: 360, rpe: 8, topic: "t_health",
      concepts: ["c_sleep","c_recall","c_spacing"],
      quotes: ["Consolidation happens offline."],
      summary: "REM and slow-wave sleep both contribute to declarative memory consolidation." },
    { id: "n27", title: "Deep work + spacing",             source_type: "blog",       source_url: "",                         date_read: D(5),  wpm: 440, rpe: 6, topic: "t_focus",
      concepts: ["c_deepwork","c_spacing","c_recall"],
      quotes: ["Schedule your reviews like meetings."],
      summary: "Deep-work blocks are the right container for spaced retrieval sessions." },
    { id: "n28", title: "Eval-driven note-taking",         source_type: "blog",       source_url: "",                         date_read: D(4),  wpm: 460, rpe: 7, topic: "t_writing",
      concepts: ["c_eval","c_atomic","c_metacog"],
      quotes: ["If you can't quiz it, you don't know it."],
      summary: "Treat each atomic note as having an implicit eval: can you produce the idea cold?" },
    { id: "n29", title: "Second-order effects of LLMs",    source_type: "essay",      source_url: "",                         date_read: D(3),  wpm: 480, rpe: 8, topic: "t_systems",
      concepts: ["c_secondorder","c_llm","c_metacog"],
      quotes: ["Cognitive offloading has a cost."],
      summary: "Outsourcing thinking to LLMs may erode metacognitive calibration." },
    { id: "n30", title: "Reading queue as a system",       source_type: "blog",       source_url: "",                         date_read: D(1),  wpm: 500, rpe: 6, topic: "t_systems",
      concepts: ["c_feedback","c_leverage","c_zettel"],
      quotes: ["Your queue is a leverage point."],
      summary: "What you choose to read next is the highest-leverage decision in a learning system." },
  ];

  return { topics, concepts, notes };
})();
