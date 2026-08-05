/* Training schedule data — edit this file to change the plan.
 *
 * type: "lift" (steel blue) | "run" (amber) | "light" (slate)
 * load: 0-100, drives the load-bar fill width
 * items: [exercise/activity, sets×reps or distance] pairs
 * Lift weights intentionally omitted — sets×reps only.
 */
const PHASES = [
  {
    "key": "p1",
    "label": "Months 1–2",
    "sub": "~7–13 mi/wk",
    "milesMin": 7, "milesMax": 13, "longRunMi": 4.5,
    "note": "Focus: frequency, not distance. Just Mon/Wed/Thu running for now — Tue & Fri stay optional/light so legs are fresh for Saturday's squat. Every 4th week, cut mileage ~25%.",
    "days": [
      { "name": "Monday", "type": "run", "title": "Easy Run", "load": 35,
        "items": [["Easy pace run", "2–2.5 mi"]],
        "note": "Conversational effort — legs still recovering from Sunday." },
      { "name": "Tuesday", "type": "light", "title": "Optional Light Work (WFH)", "load": 20,
        "items": [["DB incline press", "3×12"], ["Lateral raises", "3×15"], ["Core circuit", "10 min"]],
        "note": "Skip entirely if you'd rather just rest." },
      { "name": "Wednesday", "type": "run", "title": "Easy Run", "load": 35,
        "items": [["Easy pace run", "2–2.5 mi"]] },
      { "name": "Thursday", "type": "run", "title": "Long Run", "load": 55,
        "items": [["Long run", "3 → 4.5 mi (build weekly)"]],
        "note": "This is the one to protect — it drives the aerobic base." },
      { "name": "Friday", "type": "light", "title": "Optional Light Work (WFH)", "load": 20,
        "items": [["Barbell row or pull-ups", "3×10"], ["Curls / triceps", "3×12"]] },
      { "name": "Saturday", "type": "lift", "title": "Squat Day — Heavy", "load": 100,
        "items": [["Back Squat", "5×5"], ["Deadlift", "4×5"], ["Leg press or lunges", "3×12"], ["Hanging leg raise", "3×12"]] },
      { "name": "Sunday", "type": "lift", "title": "Bench Day — Heavy", "load": 100,
        "items": [["Bench Press", "5×5"], ["Overhead Press", "4×6"], ["Barbell Row", "4×8"], ["Close-grip bench", "3×10"]] }
    ]
  },
  {
    "key": "p2",
    "label": "Months 3–4",
    "sub": "~13–19 mi/wk",
    "milesMin": 13, "milesMax": 19, "longRunMi": 6,
    "note": "Tuesday becomes a real run day. Friday drops to lifting-only — keep it light so Saturday's squat isn't compromised. Long run climbs toward 6 mi.",
    "days": [
      { "name": "Monday", "type": "run", "title": "Easy Run", "load": 40,
        "items": [["Easy pace run", "2.5–3 mi"]] },
      { "name": "Tuesday", "type": "run", "title": "Easy Run (WFH)", "load": 40,
        "items": [["Easy pace run", "2–3 mi"]],
        "note": "Add light accessory work after, if energy allows." },
      { "name": "Wednesday", "type": "run", "title": "Easy Run", "load": 40,
        "items": [["Easy pace run", "2.5–3 mi"]] },
      { "name": "Thursday", "type": "run", "title": "Long Run", "load": 65,
        "items": [["Long run", "5 → 6 mi (build weekly)"]] },
      { "name": "Friday", "type": "light", "title": "Lifting Only (WFH)", "load": 20,
        "items": [["DB bench or OHP", "3×10"], ["Lat pulldown", "3×12"]],
        "note": "No running — protect Saturday." },
      { "name": "Saturday", "type": "lift", "title": "Squat Day — Heavy", "load": 100,
        "items": [["Back Squat", "5×5"], ["Deadlift", "4×5"], ["Leg press or lunges", "3×12"], ["Hanging leg raise", "3×12"]] },
      { "name": "Sunday", "type": "lift", "title": "Bench Day — Heavy", "load": 100,
        "items": [["Bench Press", "5×5"], ["Overhead Press", "4×6"], ["Barbell Row", "4×8"], ["Close-grip bench", "3×10"]] }
    ]
  },
  {
    "key": "p3",
    "label": "Months 5–6",
    "sub": "~19–25 mi/wk",
    "milesMin": 19, "milesMax": 25, "longRunMi": 7,
    "note": "Friday adds a short shakeout run. Keep it easy — Saturday's heavy squat is still the priority. Long run reaches 7 mi+, matching the 2024 peak, this time built safely.",
    "days": [
      { "name": "Monday", "type": "run", "title": "Easy Run", "load": 48,
        "items": [["Easy pace run", "3–3.5 mi"]] },
      { "name": "Tuesday", "type": "run", "title": "Easy Run (WFH)", "load": 48,
        "items": [["Easy pace run", "3–3.5 mi"]] },
      { "name": "Wednesday", "type": "run", "title": "Easy Run", "load": 48,
        "items": [["Easy pace run", "3–3.5 mi"]] },
      { "name": "Thursday", "type": "run", "title": "Long Run", "load": 75,
        "items": [["Long run", "6.5 → 7+ mi"]],
        "note": "Back to the 2024 peak distance — this time on a 6-month ramp, not 3 weeks." },
      { "name": "Friday", "type": "run", "title": "Shakeout Run + Light Lift (WFH)", "load": 30,
        "items": [["Easy shakeout run", "2 mi"], ["Light accessory only", "15–20 min"]],
        "note": "Keep it short — Saturday still comes first." },
      { "name": "Saturday", "type": "lift", "title": "Squat Day — Heavy", "load": 100,
        "items": [["Back Squat", "5×5"], ["Deadlift", "4×5"], ["Leg press or lunges", "3×12"], ["Hanging leg raise", "3×12"]] },
      { "name": "Sunday", "type": "lift", "title": "Bench Day — Heavy", "load": 100,
        "items": [["Bench Press", "5×5"], ["Overhead Press", "4×6"], ["Barbell Row", "4×8"], ["Close-grip bench", "3×10"]] }
    ]
  }
];
