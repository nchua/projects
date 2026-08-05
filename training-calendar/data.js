/* Training schedule data — edit this file to change the plan.
 *
 * type: "lift" (steel blue) | "run" (amber) | "light" (slate)
 * load: 0-100, drives the load-bar fill width
 *   heavy lift ~100 · long run 55-75 · easy run 35-48 · light/rest ~20
 *
 * NOTE: the original request's data section was truncated in transit, so
 * this schedule was reconstructed from the stated constraints (Sat/Sun
 * heavy barbell protected, Mon/Wed/Thu office-day runs, Tue/Fri WFH
 * accessory + later-phase easy runs, slow ramp capped well under the
 * 7.6 mi injury peak). Adjust freely — the UI renders whatever is here.
 */
const PHASES = [
  {
    id: "p1",
    tab: "PHASE I",
    name: "BASE",
    weeks: "WEEKS 1–8",
    focus: "Rebuild the running habit. All mileage easy, nothing long yet.",
    weeklyMiles: "6.5 MI/WK",
    cutback: "EVERY 4TH WK: −25% MILEAGE",
    days: [
      { day: "MON", where: "OFFICE", type: "run",   title: "Easy Run",
        spec: "2.0 MI · Z2 · CONVERSATIONAL", load: 38 },
      { day: "TUE", where: "WFH",    type: "light", title: "Light Accessory",
        spec: "DB OHP 3×10 · CHIN 3×6 · CORE 3 RDS", load: 22 },
      { day: "WED", where: "OFFICE", type: "run",   title: "Easy Run",
        spec: "2.5 MI · Z2", load: 42 },
      { day: "THU", where: "OFFICE", type: "run",   title: "Easy Run + Strides",
        spec: "2.0 MI · Z2 + 4×15S STRIDES", load: 40 },
      { day: "FRI", where: "WFH",    type: "light", title: "Mobility + Core",
        spec: "HIPS/ANKLES 20 MIN · CORE 3 RDS", load: 20 },
      { day: "SAT", where: "GYM",    type: "lift",  title: "Heavy Lower",
        spec: "SQ 5×5 · RDL 3×8 · BSS 3×10", load: 100 },
      { day: "SUN", where: "GYM",    type: "lift",  title: "Heavy Upper",
        spec: "BP 5×5 · OHP 3×8 · ROW 4×8", load: 95 },
    ],
  },
  {
    id: "p2",
    tab: "PHASE II",
    name: "BUILD",
    weeks: "WEEKS 9–16",
    focus: "Introduce the long run. Optional WFH shakeout when fresh.",
    weeklyMiles: "11 MI/WK",
    cutback: "EVERY 4TH WK: −25% MILEAGE",
    days: [
      { day: "MON", where: "OFFICE", type: "run",   title: "Easy Run",
        spec: "2.5 MI · Z2", load: 40 },
      { day: "TUE", where: "WFH",    type: "light", title: "Accessory + Opt. Shakeout",
        spec: "DB BENCH 3×10 · CHIN 3×8 · +1.5 MI EASY (OPT)", load: 30 },
      { day: "WED", where: "OFFICE", type: "run",   title: "Easy Run + Strides",
        spec: "3.0 MI · Z2 + 6×20S STRIDES", load: 46 },
      { day: "THU", where: "OFFICE", type: "run",   title: "Long Run",
        spec: "4.0 MI · Z2 · FUEL BEFORE", load: 60 },
      { day: "FRI", where: "WFH",    type: "light", title: "Light Accessory",
        spec: "LAT RAISE 3×12 · CURL 3×12 · CORE", load: 22 },
      { day: "SAT", where: "GYM",    type: "lift",  title: "Heavy Lower",
        spec: "SQ 5×5 · DL 3×5 · BSS 3×10", load: 100 },
      { day: "SUN", where: "GYM",    type: "lift",  title: "Heavy Upper",
        spec: "BP 5×5 · OHP 3×8 · ROW 4×8 · DIP 3×10", load: 95 },
    ],
  },
  {
    id: "p3",
    tab: "PHASE III",
    name: "PEAK",
    weeks: "WEEKS 17–24",
    focus: "Five run days. Long run capped at 6.0 — stays under the 7.6 that caused the 2024 injury.",
    weeklyMiles: "15 MI/WK",
    cutback: "EVERY 4TH WK: −25% MILEAGE",
    days: [
      { day: "MON", where: "OFFICE", type: "run",   title: "Easy Run",
        spec: "3.0 MI · Z2", load: 44 },
      { day: "TUE", where: "WFH",    type: "run",   title: "Easy Run + Accessory",
        spec: "2.5 MI · Z2 + DB BENCH 3×10 · CHIN 3×8", load: 42 },
      { day: "WED", where: "OFFICE", type: "run",   title: "Easy Run + Strides",
        spec: "3.5 MI · Z2 + 6×20S STRIDES", load: 48 },
      { day: "THU", where: "OFFICE", type: "run",   title: "Long Run",
        spec: "6.0 MI · Z2 · HARD CAP", load: 72 },
      { day: "FRI", where: "WFH",    type: "light", title: "Accessory + Mobility",
        spec: "ARMS/DELTS 3 RDS · HIPS 15 MIN", load: 24 },
      { day: "SAT", where: "GYM",    type: "lift",  title: "Heavy Lower",
        spec: "SQ 5×5 · DL 3×5 · BSS 3×10", load: 100 },
      { day: "SUN", where: "GYM",    type: "lift",  title: "Heavy Upper",
        spec: "BP 5×5 · OHP 3×8 · ROW 4×8 · DIP 3×10", load: 95 },
    ],
  },
];
