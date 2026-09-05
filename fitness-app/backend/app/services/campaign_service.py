"""
Campaign service (ARISE v3 spec §4) — the program as a first-class object.

* **Import** (§4.3): the PWA's ``data.js`` phases → arcs → hunt templates,
  with a pure, table-driven item parser (:func:`parse_item`).
* **Ramp math** (§5.2): :func:`week_target_miles` / :func:`long_run_miles_for_week`
  mirror the PWA's ``expectedMiles()`` (linear ramp across the arc, every
  ``deload_every_n_weeks``-th week × ``deload_factor``), with the Coach's
  ``overrides`` honored.
* **Materialization + linking** (§4.4): lazy, idempotent; a logged session
  links to the same-day hunt of its type, else the nearest within ±2 days
  (→ ``moved``); adherence XP per §13.
* **Coach applier primitives** (§8.4): ``apply_*`` re-prescribe affected
  future ``planned`` hunts only and raise ``ValueError`` with a human
  message when out of bounds.
"""
from __future__ import annotations

import copy
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.api.calendar import _is_run
from app.models.campaign import (
    Campaign,
    CampaignArc,
    CampaignSource,
    CampaignStatus,
    HuntTemplate,
    HuntType,
    PlannedHunt,
    PlannedHuntStatus,
)
from app.models.exercise_family import ExerciseFamily
from app.models.workout import WorkoutSession
from app.services import prescription_service
from app.services.exercise_family_defs import FAMILY_DEFS, family_for_name, normalize_name
from app.services.exercise_family_service import family_for_exercise
from app.services.prescription_service import Prescription, session_local_day
from app.services.xp_service import award_xp

METERS_PER_MILE = 1609.344

# ── XP economy (§13) ──
XP_HUNT_DONE = 40
XP_HUNT_MODIFIED = 25
XP_WEEK_ON_PLAN = 150
XP_GUARD_RESPECTED = 30
RUN_DONE_FRACTION = 0.80
LINK_WINDOW_DAYS = 2
MATERIALIZE_AHEAD_DAYS = 13     # the requested week + 7 days

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}

# Names in the owner's plan that the seed's canonical/alias index does not
# spell exactly. Checked after ``family_for_name`` (spec §4.3).
SYNONYMS: Dict[str, str] = {
    "db incline press": "incline_db_bench_press",
    "incline db press": "incline_db_bench_press",
    "db incline bench": "incline_db_bench_press",
    "lat pulldown": "lat_pulldown",
    "lat pulldowns": "lat_pulldown",
    "close-grip bench": "close_grip_bench",
    "close grip bench": "close_grip_bench",
    "cgbp": "close_grip_bench",
    "curls": "db_curl",
    "curl": "db_curl",
    "bicep curls": "db_curl",
    "triceps": "tricep_pushdown",
    "tricep": "tricep_pushdown",
    "tricep pushdowns": "tricep_pushdown",
    "ohp": "overhead_press",
    "db bench": "db_bench_press",
    "db bench press": "db_bench_press",
    "lunges": "lunge",
    "walking lunges": "lunge",
    "pull-ups": "pull_up",
    "pull ups": "pull_up",
    "pullups": "pull_up",
    "chin-ups": "pull_up",
    "hanging leg raise": "hanging_leg_raise",
    "hanging leg raises": "hanging_leg_raise",
    "lateral raises": "lateral_raise",
    "leg press": "leg_press",
    "rows": "barbell_row",
    "bb row": "barbell_row",
    "rdl": "romanian_deadlift",
    "squat": "back_squat",
    "squats": "back_squat",
    "bench": "bench_press",
}

_SETS_REPS = re.compile(r"^\s*(\d+)\s*[×xX]\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*$")
_RUN_RANGE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*\+?\s*mi\b")
_RUN_BUILD = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:→|->)\s*(\d+(?:\.\d+)?)\s*\+?\s*mi\b")
_RUN_SINGLE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\+?\s*mi\b")
_TIME = re.compile(r"\bmin(?:ute)?s?\b", re.IGNORECASE)
_ALT_SPLIT = re.compile(r"\s+or\s+|\s*/\s*", re.IGNORECASE)
_MONTHS = re.compile(r"months?\s+(\d+)\s*[-–]\s*(\d+)", re.IGNORECASE)
_WFH = re.compile(r"\s*\(\s*WFH\s*\)", re.IGNORECASE)


# ═══════════════════════════════════════════════════════════════════════════
# Import parser (pure)
# ═══════════════════════════════════════════════════════════════════════════

def resolve_family(name: str) -> Optional[str]:
    """Name → family slug: the seed index first, then the synonyms table."""
    fam = family_for_name(name)
    if fam:
        return fam
    return SYNONYMS.get(normalize_name(name))


def arc_weeks_from_label(label: Optional[str], fallback: int = 8) -> int:
    """``"Months 1–2"`` → 8 weeks ((b − a + 1) × 4); anything else → fallback."""
    if not label:
        return fallback
    m = _MONTHS.search(label)
    if not m:
        return fallback
    a, b = int(m.group(1)), int(m.group(2))
    if b < a:
        return fallback
    return (b - a + 1) * 4


def parse_run_spec(name: str, spec: str) -> Optional[Dict[str, Any]]:
    """``"2–2.5 mi"`` → easy ``[2, 2.5]``; ``"3 → 4.5 mi (build weekly)"`` → long "arc"."""
    lowered = (name or "").lower()
    if "shakeout" in lowered:
        kind = "shakeout"
    elif "long" in lowered:
        kind = "long"
    else:
        kind = "easy"
    m = _RUN_BUILD.match(spec)
    if m:
        return {"run": "long" if kind != "shakeout" else kind, "miles": "arc"}
    m = _RUN_RANGE.match(spec)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return {"run": kind, "miles": [lo, hi]}
    m = _RUN_SINGLE.match(spec)
    if m:
        v = float(m.group(1))
        return {"run": kind, "miles": [v, v]}
    return None


def parse_item(
    name: str,
    spec: str,
    *,
    day_type: str,
    lift_index: int,
    increment_for=None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse one ``[name, spec]`` pair from data.js into a template item.

    Returns ``(item, warning)``. ``lift_index`` is the 0-based position of
    this item among the day's *lift* items (role assignment). Unresolvable
    names come back as ``{"note": "<name> — <spec>", "unparsed": True}`` so
    nothing is silently dropped (spec §4.3).
    """
    name = (name or "").strip()
    spec = (spec or "").strip()
    increment_for = increment_for or (lambda fam: FAMILY_DEFS.get(fam, {}).get("increment_lb", 5.0))

    run = parse_run_spec(name, spec) if "mi" in spec.lower() else None
    if run is not None:
        return run, None

    if _TIME.search(spec) and not _SETS_REPS.match(spec):
        return {"note": f"{name} — {spec}"}, None

    m = _SETS_REPS.match(spec)
    if not m:
        return (
            {"note": f"{name} — {spec}", "unparsed": True},
            f"could not parse spec '{spec}' for '{name}'",
        )
    sets = int(m.group(1))
    lo = int(m.group(2))
    hi = int(m.group(3)) if m.group(3) else lo
    if hi < lo:
        lo, hi = hi, lo

    parts = [p.strip() for p in _ALT_SPLIT.split(name) if p.strip()] or [name]
    primary = resolve_family(parts[0])
    if primary is None:
        return (
            {"note": f"{name} — {spec}", "unparsed": True},
            f"unresolved exercise '{parts[0]}' in '{name}'",
        )
    warning = None
    alternatives: List[str] = []
    for alt in parts[1:]:
        fam = resolve_family(alt)
        if fam and fam != primary and fam not in alternatives:
            alternatives.append(fam)
        elif fam is None:
            warning = f"unresolved alternative '{alt}' in '{name}' (dropped)"

    if day_type == HuntType.LIFT.value:
        role = "main" if lift_index == 0 else ("secondary" if lift_index == 1 else "accessory")
    else:
        role = "accessory"
    progression = "linear" if role in ("main", "secondary") and hi <= 6 else "double"
    item: Dict[str, Any] = {
        "family": primary,
        "sets": sets,
        "reps": [lo, hi],
        "role": role,
        "progression": progression,
        "increment_lb": float(increment_for(primary)),
        "rpe_cap": 8 if role == "main" else 9,
    }
    if alternatives:
        item["alternatives"] = alternatives
    return item, warning


def parse_day(day: Dict[str, Any], increment_for=None) -> Tuple[Dict[str, Any], List[str]]:
    """One ``days[]`` entry → a HuntTemplate payload + warnings."""
    warnings: List[str] = []
    day_name = str(day.get("name") or "").strip().lower()
    weekday = WEEKDAYS.get(day_name)
    if weekday is None:
        raise ValueError(f"unknown weekday '{day.get('name')}'")
    day_type = str(day.get("type") or "light").lower()
    if day_type not in {t.value for t in HuntType}:
        warnings.append(f"{day.get('name')}: unknown type '{day_type}', imported as light")
        day_type = HuntType.LIGHT.value
    title = str(day.get("title") or day_type.title())
    location_tag = "WFH" if _WFH.search(title) else None
    clean_title = _WFH.sub("", title).strip() or title

    items: List[Dict[str, Any]] = []
    lift_index = 0
    for pair in day.get("items") or []:
        if not pair:
            continue
        name = str(pair[0]) if len(pair) > 0 else ""
        spec = str(pair[1]) if len(pair) > 1 else ""
        item, warning = parse_item(
            name, spec, day_type=day_type, lift_index=lift_index, increment_for=increment_for
        )
        if warning:
            warnings.append(f"{day.get('name')}: {warning}")
        if item.get("family"):
            lift_index += 1
        items.append(item)
    return {
        "weekday": weekday,
        "type": day_type,
        "title": clean_title,
        "location_tag": location_tag,
        "load_hint": day.get("load"),
        "items": items,
        "note": day.get("note"),
    }, warnings


def parse_phases(phases: Sequence[Dict[str, Any]], increment_for=None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """The whole ``PHASES`` array → arc payloads (with ``templates``) + warnings."""
    arcs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for index, phase in enumerate(phases):
        templates = []
        for day in phase.get("days") or []:
            tmpl, w = parse_day(day, increment_for)
            templates.append(tmpl)
            warnings.extend(f"{phase.get('label') or index + 1} · {x}" for x in w)
        arcs.append({
            "index": index,
            "name": str(phase.get("label") or f"Arc {index + 1}"),
            "weeks": arc_weeks_from_label(phase.get("label")),
            "run_miles_min": phase.get("milesMin"),
            "run_miles_max": phase.get("milesMax"),
            "long_run_miles": phase.get("longRunMi"),
            "notes": " · ".join(x for x in (phase.get("sub"), phase.get("note")) if x) or None,
            "templates": templates,
        })
    return arcs, warnings


# ═══════════════════════════════════════════════════════════════════════════
# Campaign lookups + ramp math
# ═══════════════════════════════════════════════════════════════════════════

def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def get_active_campaign(db: Session, user_id: str) -> Optional[Campaign]:
    return (
        db.query(Campaign)
        .options(joinedload(Campaign.arcs).joinedload(CampaignArc.templates))
        .filter(Campaign.user_id == user_id, Campaign.status == CampaignStatus.ACTIVE.value)
        .order_by(Campaign.created_at.desc())
        .first()
    )


def get_campaign(db: Session, user_id: str, campaign_id: str) -> Optional[Campaign]:
    return (
        db.query(Campaign)
        .options(joinedload(Campaign.arcs).joinedload(CampaignArc.templates))
        .filter(Campaign.user_id == user_id, Campaign.id == campaign_id)
        .first()
    )


def campaign_anchor(campaign: Campaign) -> date:
    """Monday of the campaign's first week — the week-index origin."""
    return monday_of(campaign.start_date)


def total_weeks(campaign: Campaign) -> int:
    return sum(int(arc.weeks or 0) for arc in campaign.arcs)


def campaign_end_date(campaign: Campaign) -> date:
    return campaign_anchor(campaign) + timedelta(weeks=total_weeks(campaign)) - timedelta(days=1)


def arc_bounds(campaign: Campaign) -> List[Tuple[CampaignArc, date, date]]:
    """[(arc, first Monday, last Sunday)] in index order."""
    out = []
    cursor = campaign_anchor(campaign)
    for arc in sorted(campaign.arcs, key=lambda a: a.index):
        end = cursor + timedelta(weeks=int(arc.weeks or 0)) - timedelta(days=1)
        out.append((arc, cursor, end))
        cursor = end + timedelta(days=1)
    return out


def week_context(campaign: Campaign, d: date) -> Optional[Dict[str, Any]]:
    """Where ``d`` sits in the campaign, or None when outside it.

    ``{"arc", "arc_index", "week_in_arc" (0-based), "campaign_week" (1-based),
    "week_start", "deload"}``. Deload = every ``deload_every_n_weeks``-th
    week of the arc (the PWA's ``n % 4 == 0`` cutback) or a Coach-forced week.
    """
    if d < campaign.start_date:
        return None
    week_start = monday_of(d)
    campaign_week0 = (week_start - campaign_anchor(campaign)).days // 7
    cursor = 0
    for arc in sorted(campaign.arcs, key=lambda a: a.index):
        weeks = int(arc.weeks or 0)
        if campaign_week0 < cursor + weeks:
            wip = campaign_week0 - cursor
            forced = set((campaign.overrides or {}).get("deload_weeks") or [])
            cadence = int(arc.deload_every_n_weeks or 4)
            deload = ((wip + 1) % cadence == 0) or (week_start.isoformat() in forced)
            return {
                "arc": arc,
                "arc_index": arc.index,
                "week_in_arc": wip,
                "campaign_week": campaign_week0 + 1,
                "week_start": week_start,
                "deload": deload,
            }
        cursor += weeks
    return None


def _ramp(lo: Optional[float], hi: Optional[float], wip: int, weeks: int) -> Optional[float]:
    if lo is None and hi is None:
        return None
    lo = float(lo if lo is not None else hi)
    hi = float(hi if hi is not None else lo)
    if weeks <= 1:
        return hi
    return lo + (hi - lo) * (min(wip, weeks - 1) / (weeks - 1))


def week_target_miles(
    db: Session, campaign: Campaign, week_start: date, *, include_deload: bool = True
) -> Optional[float]:
    """The arc ramp for that week (deload applied, ``overrides["week_miles"]`` wins)."""
    _ = db
    week_start = monday_of(week_start)
    override = ((campaign.overrides or {}).get("week_miles") or {}).get(week_start.isoformat())
    if override is not None:
        return round(float(override), 1)
    ctx = week_context(campaign, max(week_start, campaign.start_date))
    if ctx is None or ctx["week_start"] != week_start:
        return None
    arc = ctx["arc"]
    base = _ramp(arc.run_miles_min, arc.run_miles_max, ctx["week_in_arc"], int(arc.weeks or 1))
    if base is None:
        return None
    if ctx["deload"] and include_deload:
        base *= float(arc.deload_factor or 0.75)
    return round(base, 1)


def long_run_miles_for_week(
    campaign: Campaign, week_start: date, *, include_deload: bool = True
) -> Optional[float]:
    """The arc's ``long_run_miles`` progression for that week (spec §5.2).

    Linear from the previous arc's long run (3 mi in arc 1) up to this
    arc's ``long_run_miles`` across its weeks; deload weeks × factor.
    """
    week_start = monday_of(week_start)
    ctx = week_context(campaign, max(week_start, campaign.start_date))
    if ctx is None or ctx["week_start"] != week_start:
        return None
    arc = ctx["arc"]
    if arc.long_run_miles is None:
        return None
    arcs = sorted(campaign.arcs, key=lambda a: a.index)
    prev = next((a for a in reversed(arcs) if a.index < arc.index and a.long_run_miles), None)
    start = float(prev.long_run_miles) if prev else 3.0
    end = float(arc.long_run_miles)
    if start > end:
        start = end
    val = _ramp(start, end, ctx["week_in_arc"], int(arc.weeks or 1))
    if val is None:
        return None
    if ctx["deload"] and include_deload:
        val *= float(arc.deload_factor or 0.75)
    return round(val, 1)


def _templates_by_weekday(arc: CampaignArc) -> Dict[int, HuntTemplate]:
    out: Dict[int, HuntTemplate] = {}
    for t in arc.templates:
        out.setdefault(int(t.weekday), t)
    return out


def template_families(template: HuntTemplate) -> Dict[str, List[str]]:
    """``{"main": [...], "secondary": [...], "accessory": [...]}`` family slugs."""
    out: Dict[str, List[str]] = {"main": [], "secondary": [], "accessory": []}
    for item in template.items or []:
        fam = item.get("family")
        if not fam:
            continue
        role = item.get("role") or "accessory"
        out.setdefault(role, []).append(fam)
    return out


def template_has_family(template: HuntTemplate, family_id: str) -> bool:
    return any(it.get("family") == family_id for it in (template.items or []))


# ═══════════════════════════════════════════════════════════════════════════
# Import
# ═══════════════════════════════════════════════════════════════════════════

def _increment_lookup(db: Session):
    rows = {f.id: float(f.increment_lb) for f in db.query(ExerciseFamily).all()}

    def _for(fam: str) -> float:
        if fam in rows:
            return rows[fam]
        return float(FAMILY_DEFS.get(fam, {}).get("increment_lb", 5.0))
    return _for


def retire_campaign(db: Session, campaign: Campaign) -> int:
    """Mark a campaign completed and delete its future ``planned`` hunts."""
    campaign.status = CampaignStatus.COMPLETED.value
    deleted = (
        db.query(PlannedHunt)
        .filter(
            PlannedHunt.campaign_id == campaign.id,
            PlannedHunt.status == PlannedHuntStatus.PLANNED.value,
            PlannedHunt.session_id.is_(None),
        )
        .delete(synchronize_session=False)
    )
    db.flush()
    return int(deleted or 0)


def import_campaign(
    db: Session,
    user_id: str,
    *,
    name: str,
    phases: Sequence[Dict[str, Any]],
    start_date: Optional[date] = None,
    client_date: Optional[date] = None,
    goal: Optional[str] = None,
    replace: bool = False,
) -> Tuple[Campaign, List[str], int]:
    """POST /campaign/import body → Campaign + arcs + templates.

    Raises ``ValueError("active campaign exists")`` when one is active and
    ``replace`` is false (the API maps it to 409).
    """
    active = get_active_campaign(db, user_id)
    if active is not None:
        if not replace:
            raise ValueError("active campaign exists")
        retire_campaign(db, active)

    today = client_date or date.today()
    start = start_date or monday_of(today)
    arcs, warnings = parse_phases(phases, _increment_lookup(db))

    campaign = Campaign(
        user_id=user_id, name=name, goal=goal, start_date=start,
        status=CampaignStatus.ACTIVE.value, source=CampaignSource.IMPORT.value, overrides={},
    )
    db.add(campaign)
    db.flush()
    templates_created = 0
    for arc_data in arcs:
        templates = arc_data.pop("templates")
        arc = CampaignArc(campaign_id=campaign.id, deload_every_n_weeks=4, deload_factor=0.75, **arc_data)
        db.add(arc)
        db.flush()
        for tmpl in templates:
            db.add(HuntTemplate(arc_id=arc.id, **tmpl))
            templates_created += 1
    db.flush()
    db.expire(campaign, ["arcs"])
    return get_campaign(db, user_id, campaign.id), warnings, templates_created


def create_campaign(
    db: Session,
    user_id: str,
    *,
    name: str,
    arcs: Sequence[Dict[str, Any]],
    start_date: Optional[date] = None,
    client_date: Optional[date] = None,
    goal: Optional[str] = None,
) -> Campaign:
    """POST /campaign — minimal manual create (arcs only, no templates)."""
    if get_active_campaign(db, user_id) is not None:
        raise ValueError("active campaign exists")
    today = client_date or date.today()
    campaign = Campaign(
        user_id=user_id, name=name, goal=goal, start_date=start_date or monday_of(today),
        status=CampaignStatus.ACTIVE.value, source=CampaignSource.TEMPLATE.value, overrides={},
    )
    db.add(campaign)
    db.flush()
    for index, arc in enumerate(arcs):
        db.add(CampaignArc(campaign_id=campaign.id, index=index, **arc))
    db.flush()
    return get_campaign(db, user_id, campaign.id)


# ═══════════════════════════════════════════════════════════════════════════
# Materialization (§4.4)
# ═══════════════════════════════════════════════════════════════════════════

def _hunt_query(db: Session, user_id: str):
    return (
        db.query(PlannedHunt)
        .options(
            joinedload(PlannedHunt.template),
            joinedload(PlannedHunt.arc),
            joinedload(PlannedHunt.campaign),
        )
        .filter(PlannedHunt.user_id == user_id)
    )


def _guard_lines(rationale: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [ln for ln in (rationale or []) if str(ln.get("key", "")).startswith("guard:")]


def prescribe_and_store(db: Session, hunt: PlannedHunt) -> bool:
    """Compute the base prescription and persist it when it changed.

    Keeps any guard lines already appended to ``rationale`` (they are keyed
    by flag and written at fetch time). Returns True when a write happened.
    """
    p = prescription_service.prescribe(db, hunt, condition=None, guard_flags=[], gate=None)
    new = p.base
    if hunt.prescription == new:
        return False
    hunt.prescription = new
    hunt.rationale = list(p.base_rationale) + _guard_lines(hunt.rationale)
    hunt.prescription_version = int(hunt.prescription_version or 0) + 1
    hunt.generated_at = datetime.now(timezone.utc)
    return True


def append_guard_rationale(hunt: PlannedHunt, prescription: Prescription) -> bool:
    """Write the guard's rationale lines into ``planned_hunts.rationale`` (§6.4), keyed by flag."""
    existing = list(hunt.rationale or [])
    keys = {ln.get("key") for ln in existing}
    changed = False
    for ln in _guard_lines(prescription.rationale):
        if ln["key"] in keys:
            for i, old in enumerate(existing):
                if old.get("key") == ln["key"] and old != ln:
                    existing[i] = ln
                    changed = True
            continue
        existing.append(ln)
        keys.add(ln["key"])
        changed = True
    if changed:
        hunt.rationale = existing
        flag_modified(hunt, "rationale")
    return changed


def materialize_range(
    db: Session, user_id: str, start: date, end: date, *, today: Optional[date] = None
) -> List[PlannedHunt]:
    """Create missing planned hunts in ``[start, end]``; idempotent.

    Also refreshes the base prescription of future ``planned`` hunts in the
    range (anchors move as sessions land) and flips past ``planned`` rows to
    ``skipped``. Returns every hunt in the range, oldest first.
    """
    today = today or date.today()
    campaign = get_active_campaign(db, user_id)
    if campaign is None:
        return []
    existing = _hunt_query(db, user_id).filter(
        PlannedHunt.campaign_id == campaign.id,
        PlannedHunt.date >= start,
        PlannedHunt.date <= end,
    ).all()
    by_key = {(h.date, h.template_id): h for h in existing}
    templates_by_arc = {arc.id: _templates_by_weekday(arc) for arc in campaign.arcs}

    created: List[PlannedHunt] = []
    d = start
    while d <= end:
        ctx = week_context(campaign, d)
        if ctx is not None:
            tmpl = templates_by_arc.get(ctx["arc"].id, {}).get(d.weekday())
            if tmpl is not None and tmpl.type != HuntType.REST.value and (d, tmpl.id) not in by_key:
                hunt = PlannedHunt(
                    user_id=user_id, campaign_id=campaign.id, arc_id=ctx["arc"].id,
                    template_id=tmpl.id, date=d, week_start=ctx["week_start"],
                    week_target_miles=week_target_miles(db, campaign, ctx["week_start"]),
                    status=PlannedHuntStatus.PLANNED.value,
                )
                hunt.template = tmpl
                hunt.arc = ctx["arc"]
                hunt.campaign = campaign
                db.add(hunt)
                created.append(hunt)
                by_key[(d, tmpl.id)] = hunt
        d += timedelta(days=1)
    if created:
        db.flush()

    for hunt in by_key.values():
        if hunt.status != PlannedHuntStatus.PLANNED.value:
            continue
        if hunt.date < today:
            hunt.status = PlannedHuntStatus.SKIPPED.value
            continue
        prescribe_and_store(db, hunt)
    db.flush()
    return sorted(by_key.values(), key=lambda h: (h.date, h.template.weekday if h.template else 0))


def hunt_on(db: Session, user_id: str, d: date) -> Optional[PlannedHunt]:
    """The planned hunt for a day (the active campaign's), or None."""
    campaign = get_active_campaign(db, user_id)
    if campaign is None:
        return None
    rows = _hunt_query(db, user_id).filter(
        PlannedHunt.campaign_id == campaign.id, PlannedHunt.date == d
    ).all()
    if not rows:
        return None
    rows.sort(key=lambda h: (0 if h.status != PlannedHuntStatus.MOVED.value else 1, h.created_at or datetime.min))
    return rows[0]


def next_planned_hunt_with_family(
    db: Session, user_id: str, family_id: str, after: date
) -> Optional[PlannedHunt]:
    """First ``planned`` hunt after ``after`` whose template includes the family.

    Materializes two weeks past ``after`` first so the gate engine always
    sees next week's hunts.
    """
    materialize_range(db, user_id, after + timedelta(days=1), after + timedelta(days=14), today=after)
    rows = (
        _hunt_query(db, user_id)
        .filter(PlannedHunt.date > after, PlannedHunt.status == PlannedHuntStatus.PLANNED.value)
        .order_by(PlannedHunt.date.asc())
        .all()
    )
    for hunt in rows:
        if hunt.template is not None and template_has_family(hunt.template, family_id):
            return hunt
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Linking (§4.4) + adherence XP (§13)
# ═══════════════════════════════════════════════════════════════════════════

def session_kind(session: WorkoutSession) -> Optional[str]:
    """``lift`` when the session has sets; ``run`` per ``api/calendar._is_run``; else None."""
    if any(we.sets for we in (session.workout_exercises or [])):
        return HuntType.LIFT.value
    if _is_run(session.activity_type) or (session.activity_type is None and session.distance_meters):
        return HuntType.RUN.value
    return None


def _compatible(hunt_type: str, kind: str) -> bool:
    return hunt_type == kind or hunt_type == HuntType.LIGHT.value


def session_miles(session: WorkoutSession) -> float:
    return round(float(session.distance_meters or 0) / METERS_PER_MILE, 2)


def _set_overrides(campaign: Campaign, **updates: Any) -> None:
    merged = dict(campaign.overrides or {})
    merged.update(updates)
    campaign.overrides = merged
    flag_modified(campaign, "overrides")


def _run_bound_miles(hunt: PlannedHunt) -> Optional[float]:
    """The prescribed lower bound a run is judged against (a guard cut wins)."""
    cut = None
    for ln in _guard_lines(hunt.rationale):
        val = (ln.get("numbers") or {}).get("cut_miles")
        if val is not None:
            cut = float(val) if cut is None else min(cut, float(val))
    if cut is not None:
        return cut
    run = (hunt.prescription or {}).get("run") if hunt.prescription else None
    if run and run.get("miles") is not None:
        return float(run["miles"])
    for item in (hunt.template.items if hunt.template else None) or []:
        if item.get("run"):
            m = item.get("miles")
            if isinstance(m, (list, tuple)) and m:
                return float(m[0])
            return None
    return None


def link_status(db: Session, hunt: PlannedHunt, session: WorkoutSession, kind: str) -> str:
    """``done`` vs ``modified`` for a same-day link (spec §4.4)."""
    template = hunt.template
    if kind == HuntType.RUN.value:
        has_run_item = any(it.get("run") for it in (template.items or []))
        if template.type == HuntType.LIGHT.value and not has_run_item:
            # A run on a lifting-only light day: something happened, not the plan.
            return PlannedHuntStatus.MODIFIED.value
        bound = _run_bound_miles(hunt)
        if not bound:
            return PlannedHuntStatus.DONE.value
        return (
            PlannedHuntStatus.DONE.value
            if session_miles(session) >= RUN_DONE_FRACTION * bound
            else PlannedHuntStatus.MODIFIED.value
        )
    session_fams = set()
    for we in session.workout_exercises or []:
        fam = family_for_exercise(db, we.exercise_id)
        if fam:
            session_fams.add(fam)
    required = [
        item for item in (template.items or [])
        if item.get("family") and (item.get("role") or "accessory") in ("main", "secondary")
    ]
    if not required:
        # Light days carry accessories only: done when the session shares at
        # least one of the template's families (else it was a different hunt).
        offered = set()
        for item in template.items or []:
            if item.get("family"):
                offered |= {item["family"], *(item.get("alternatives") or [])}
        if offered and not (offered & session_fams):
            return PlannedHuntStatus.MODIFIED.value
        return PlannedHuntStatus.DONE.value
    for item in required:
        accepted = {item["family"], *(item.get("alternatives") or [])}
        if not accepted & session_fams:
            return PlannedHuntStatus.MODIFIED.value
    return PlannedHuntStatus.DONE.value


def _find_hunt_for_session(
    db: Session, session: WorkoutSession, day: date, kind: str
) -> Optional[PlannedHunt]:
    candidates = (
        _hunt_query(db, session.user_id)
        .filter(
            PlannedHunt.session_id.is_(None),
            PlannedHunt.status.in_([PlannedHuntStatus.PLANNED.value, PlannedHuntStatus.SKIPPED.value]),
            PlannedHunt.date >= day - timedelta(days=LINK_WINDOW_DAYS),
            PlannedHunt.date <= day + timedelta(days=LINK_WINDOW_DAYS),
        )
        .all()
    )
    candidates = [h for h in candidates if h.template and _compatible(h.template.type, kind)]
    if not candidates:
        return None

    def _rank(h: PlannedHunt):
        fit = 0 if link_status(db, h, session, kind) == PlannedHuntStatus.DONE.value else 1
        delta = (h.date - day).days
        return (
            fit,                                   # the hunt the session actually is
            0 if delta == 0 else 1,                # same day
            0 if h.template.type == kind else 1,   # exact type over light
            abs(delta),                            # nearest
            0 if delta < 0 else 1,                 # making up a missed hunt first
        )

    return sorted(candidates, key=_rank)[0]


def link_session_to_plan(
    db: Session, session: WorkoutSession, *, planned_hunt_id: Optional[str] = None
) -> Dict[str, Any]:
    """Link a logged session to its planned hunt; award adherence XP (§13).

    Returns ``{"planned_hunt_id", "planned_hunt_status"}`` or ``{}`` when
    nothing matched. Idempotent per session: a second call returns the
    existing link without re-awarding.
    """
    already = db.query(PlannedHunt).filter(PlannedHunt.session_id == session.id).first()
    if already is not None:
        return {"planned_hunt_id": already.id, "planned_hunt_status": already.status}
    day = session_local_day(session)
    kind = session_kind(session)
    if day is None or kind is None:
        return {}

    hunt: Optional[PlannedHunt] = None
    if planned_hunt_id:
        explicit = _hunt_query(db, session.user_id).filter(PlannedHunt.id == planned_hunt_id).first()
        if explicit is not None and explicit.session_id is None and explicit.template is not None:
            hunt = explicit
    if hunt is None:
        # Two sessions in one day: the first links, the second is free-form.
        taken = db.query(PlannedHunt.id).filter(
            PlannedHunt.user_id == session.user_id,
            PlannedHunt.session_id.isnot(None),
            (PlannedHunt.date == day) | (PlannedHunt.moved_to == day),
        ).first()
        if taken is not None:
            return {}
        hunt = _find_hunt_for_session(db, session, day, kind)
    if hunt is None:
        return {}

    status = link_status(db, hunt, session, kind)
    if hunt.date != day:
        status = PlannedHuntStatus.MOVED.value
        hunt.moved_to = day
    hunt.session_id = session.id
    hunt.status = status
    db.flush()

    xp = XP_HUNT_DONE if status == PlannedHuntStatus.DONE.value else XP_HUNT_MODIFIED
    award_xp(db, session.user_id, xp, count_workout=False)

    if kind == HuntType.RUN.value:
        cuts = [
            float((ln.get("numbers") or {}).get("cut_miles"))
            for ln in _guard_lines(hunt.rationale)
            if (ln.get("numbers") or {}).get("cut_miles") is not None
        ]
        if cuts and session_miles(session) <= min(cuts) + 0.05:
            award_xp(db, session.user_id, XP_GUARD_RESPECTED, count_workout=False)

    campaign = hunt.campaign or db.query(Campaign).filter(Campaign.id == hunt.campaign_id).first()
    if campaign is not None and hunt.week_start is not None:
        week_iso = hunt.week_start.isoformat()
        awarded = list((campaign.overrides or {}).get("week_bonus_awarded") or [])
        if week_iso not in awarded:
            week_rows = db.query(PlannedHunt.status).filter(
                PlannedHunt.campaign_id == campaign.id, PlannedHunt.week_start == hunt.week_start
            ).all()
            finished = {PlannedHuntStatus.DONE.value, PlannedHuntStatus.MODIFIED.value, PlannedHuntStatus.MOVED.value}
            if week_rows and all(r[0] in finished for r in week_rows):
                award_xp(db, session.user_id, XP_WEEK_ON_PLAN, count_workout=False)
                _set_overrides(campaign, week_bonus_awarded=awarded + [week_iso])
    db.flush()
    return {"planned_hunt_id": hunt.id, "planned_hunt_status": status}


# ═══════════════════════════════════════════════════════════════════════════
# Coach applier primitives (§8.4) + in-app edits (§4.3)
# ═══════════════════════════════════════════════════════════════════════════

def _future_planned(db: Session, campaign: Campaign, today: date, *, week_start: Optional[date] = None):
    q = _hunt_query(db, campaign.user_id).filter(
        PlannedHunt.campaign_id == campaign.id,
        PlannedHunt.status == PlannedHuntStatus.PLANNED.value,
        PlannedHunt.date >= today,
    )
    if week_start is not None:
        q = q.filter(PlannedHunt.week_start == monday_of(week_start))
    return q.order_by(PlannedHunt.date.asc()).all()


def refresh_planned_hunts(db: Session, campaign: Campaign, hunts: Iterable[PlannedHunt]) -> List[str]:
    """Recompute arc/template/week target and re-prescribe; drop rows that no longer apply."""
    templates_by_arc = {arc.id: _templates_by_weekday(arc) for arc in campaign.arcs}
    affected: List[str] = []
    for hunt in list(hunts):
        ctx = week_context(campaign, hunt.date)
        tmpl = templates_by_arc.get(ctx["arc"].id, {}).get(hunt.date.weekday()) if ctx else None
        if ctx is None or tmpl is None:
            affected.append(hunt.id)
            db.delete(hunt)
            continue
        if hunt.arc_id != ctx["arc"].id or hunt.template_id != tmpl.id:
            hunt.arc_id = ctx["arc"].id
            hunt.template_id = tmpl.id
            hunt.arc = ctx["arc"]
            hunt.template = tmpl
        hunt.week_start = ctx["week_start"]
        hunt.week_target_miles = week_target_miles(db, campaign, ctx["week_start"])
        hunt.campaign = campaign
        prescribe_and_store(db, hunt)
        affected.append(hunt.id)
    db.flush()
    return affected


def _check_family(db: Session, family_id: str) -> None:
    if family_id in FAMILY_DEFS:
        return
    if db.query(ExerciseFamily.id).filter(ExerciseFamily.id == family_id).first():
        return
    raise ValueError(f"unknown exercise family '{family_id}'")


def _check_monday(week_start: date) -> date:
    if week_start.weekday() != 0:
        raise ValueError(f"{week_start.isoformat()} is not a Monday")
    return week_start


def apply_set_progression(
    db: Session, campaign: Campaign, family_id: str, increment_lb: float, *, today: Optional[date] = None
) -> List[str]:
    """Set the per-hunt increment for a family (0 < step ≤ 25 lb)."""
    today = today or date.today()
    _check_family(db, family_id)
    if not (0 < float(increment_lb) <= 25):
        raise ValueError("increment must be between 0 and 25 lb")
    prog = dict((campaign.overrides or {}).get("progression") or {})
    prog[family_id] = float(increment_lb)
    _set_overrides(campaign, progression=prog)
    hunts = [h for h in _future_planned(db, campaign, today) if h.template and template_has_family(h.template, family_id)]
    return refresh_planned_hunts(db, campaign, hunts)


def apply_set_week_miles(
    db: Session, campaign: Campaign, week_start: date, miles: float, *, today: Optional[date] = None
) -> List[str]:
    """Override one week's run target (0 ≤ miles ≤ 60)."""
    today = today or date.today()
    week_start = _check_monday(week_start)
    if not (0 <= float(miles) <= 60):
        raise ValueError("week miles must be between 0 and 60")
    if week_start < monday_of(today):
        raise ValueError("cannot change a week that has already passed")
    wm = dict((campaign.overrides or {}).get("week_miles") or {})
    wm[week_start.isoformat()] = round(float(miles), 1)
    _set_overrides(campaign, week_miles=wm)
    return refresh_planned_hunts(db, campaign, _future_planned(db, campaign, today, week_start=week_start))


def apply_deload_now(
    db: Session, campaign: Campaign, week_start: date, scope: str, *, today: Optional[date] = None
) -> List[str]:
    """Force a deload week (scope ∈ lifts|runs|all); records ``overrides["last_deload_week"]``."""
    today = today or date.today()
    week_start = _check_monday(week_start)
    if scope not in ("lifts", "runs", "all"):
        raise ValueError("scope must be lifts, runs or all")
    if week_start < monday_of(today):
        raise ValueError("cannot deload a week that has already passed")
    updates: Dict[str, Any] = {"last_deload_week": week_start.isoformat()}
    iso = week_start.isoformat()
    if scope in ("runs", "all"):
        weeks = list((campaign.overrides or {}).get("deload_weeks") or [])
        if iso not in weeks:
            weeks.append(iso)
        updates["deload_weeks"] = weeks
    if scope in ("lifts", "all"):
        weeks = list((campaign.overrides or {}).get("lift_deload_weeks") or [])
        if iso not in weeks:
            weeks.append(iso)
        updates["lift_deload_weeks"] = weeks
    _set_overrides(campaign, **updates)
    return refresh_planned_hunts(db, campaign, _future_planned(db, campaign, today, week_start=week_start))


def apply_swap_days(
    db: Session, campaign: Campaign, a: date, b: date, *, today: Optional[date] = None
) -> List[str]:
    """Swap the templates of two future planned days (one may be a rest day)."""
    today = today or date.today()
    if a == b:
        raise ValueError("pick two different days")
    if a < today or b < today:
        raise ValueError("both days must be today or later")
    rows = {h.date: h for h in _future_planned(db, campaign, today) if h.date in (a, b)}
    ha, hb = rows.get(a), rows.get(b)
    if ha is None and hb is None:
        raise ValueError("neither day has a planned hunt")
    if ha is not None and hb is not None:
        ha.template_id, hb.template_id = hb.template_id, ha.template_id
        ha.arc_id, hb.arc_id = hb.arc_id, ha.arc_id
        ha.template, hb.template = hb.template, ha.template
        ha.arc, hb.arc = hb.arc, ha.arc
        db.flush()
        out = []
        for h in (ha, hb):
            prescribe_and_store(db, h)
            out.append(h.id)
        db.flush()
        return out
    hunt = ha or hb
    target = b if hunt is ha else a
    ctx = week_context(campaign, target)
    if ctx is None:
        raise ValueError(f"{target.isoformat()} is outside the campaign")
    hunt.date = target
    hunt.week_start = ctx["week_start"]
    hunt.week_target_miles = week_target_miles(db, campaign, ctx["week_start"])
    db.flush()
    prescribe_and_store(db, hunt)
    db.flush()
    return [hunt.id]


def apply_extend_arc(
    db: Session, campaign: Campaign, weeks: int, *, today: Optional[date] = None
) -> List[str]:
    """Extend the current arc by 1–4 weeks; later arcs shift with it."""
    today = today or date.today()
    if not (1 <= int(weeks) <= 4):
        raise ValueError("extend by 1 to 4 weeks")
    ctx = week_context(campaign, max(today, campaign.start_date))
    arc = ctx["arc"] if ctx else (sorted(campaign.arcs, key=lambda a: a.index)[-1] if campaign.arcs else None)
    if arc is None:
        raise ValueError("campaign has no arcs")
    arc.weeks = int(arc.weeks or 0) + int(weeks)
    db.flush()
    return refresh_planned_hunts(db, campaign, _future_planned(db, campaign, today))


def apply_change_reps(
    db: Session, campaign: Campaign, family_id: str, sets: int, reps: Sequence[int], *, today: Optional[date] = None
) -> List[str]:
    """Override a family's sets × [lo, hi] (1–10 sets, 1 ≤ lo ≤ hi ≤ 30)."""
    today = today or date.today()
    _check_family(db, family_id)
    if not (1 <= int(sets) <= 10):
        raise ValueError("sets must be between 1 and 10")
    reps = [int(r) for r in reps] if reps else []
    if not reps or len(reps) > 2:
        raise ValueError("reps must be [n] or [lo, hi]")
    lo, hi = reps[0], reps[-1]
    if not (1 <= lo <= hi <= 30):
        raise ValueError("reps must satisfy 1 ≤ lo ≤ hi ≤ 30")
    table = dict((campaign.overrides or {}).get("reps") or {})
    table[family_id] = {"sets": int(sets), "reps": [lo, hi]}
    _set_overrides(campaign, reps=table)
    hunts = [h for h in _future_planned(db, campaign, today) if h.template and template_has_family(h.template, family_id)]
    return refresh_planned_hunts(db, campaign, hunts)


def skip_hunt(db: Session, hunt: PlannedHunt) -> PlannedHunt:
    if hunt.status != PlannedHuntStatus.PLANNED.value:
        raise ValueError(f"only planned hunts can be skipped (this one is {hunt.status})")
    hunt.status = PlannedHuntStatus.SKIPPED.value
    db.flush()
    return hunt


def move_hunt(db: Session, hunt: PlannedHunt, target: date) -> PlannedHunt:
    """Mark the hunt ``moved`` and materialize its template on ``target``."""
    if hunt.status != PlannedHuntStatus.PLANNED.value:
        raise ValueError(f"only planned hunts can be moved (this one is {hunt.status})")
    if target == hunt.date:
        raise ValueError("pick a different day")
    campaign = hunt.campaign or get_campaign(db, hunt.user_id, hunt.campaign_id)
    ctx = week_context(campaign, target)
    if ctx is None:
        raise ValueError(f"{target.isoformat()} is outside the campaign")
    clash = db.query(PlannedHunt).filter(
        PlannedHunt.user_id == hunt.user_id, PlannedHunt.date == target,
        PlannedHunt.template_id == hunt.template_id,
    ).first()
    if clash is not None:
        raise ValueError(f"{target.isoformat()} already has this hunt")
    hunt.status = PlannedHuntStatus.MOVED.value
    hunt.moved_to = target
    new = PlannedHunt(
        user_id=hunt.user_id, campaign_id=hunt.campaign_id, arc_id=hunt.arc_id,
        template_id=hunt.template_id, date=target, week_start=ctx["week_start"],
        week_target_miles=week_target_miles(db, campaign, ctx["week_start"]),
        status=PlannedHuntStatus.PLANNED.value,
    )
    new.template = hunt.template
    new.arc = hunt.arc
    new.campaign = campaign
    db.add(new)
    db.flush()
    prescribe_and_store(db, new)
    db.flush()
    return hunt


def swap_hunts(db: Session, hunt: PlannedHunt, other: PlannedHunt) -> PlannedHunt:
    for h in (hunt, other):
        if h.status != PlannedHuntStatus.PLANNED.value:
            raise ValueError(f"only planned hunts can be swapped ({h.date.isoformat()} is {h.status})")
    if hunt.id == other.id:
        raise ValueError("pick two different hunts")
    if hunt.template_id == other.template_id:
        raise ValueError("those two hunts are the same template")
    hunt.template_id, other.template_id = other.template_id, hunt.template_id
    hunt.arc_id, other.arc_id = other.arc_id, hunt.arc_id
    hunt.template, other.template = other.template, hunt.template
    hunt.arc, other.arc = other.arc, hunt.arc
    db.flush()
    for h in (hunt, other):
        prescribe_and_store(db, h)
    db.flush()
    return hunt


# ═══════════════════════════════════════════════════════════════════════════
# Serialization
# ═══════════════════════════════════════════════════════════════════════════

def campaign_to_dict(db: Session, campaign: Campaign, client_date: Optional[date] = None) -> Dict[str, Any]:
    today = client_date or date.today()
    ctx = week_context(campaign, today)
    bounds = arc_bounds(campaign)
    week_start = monday_of(today)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "goal": campaign.goal,
        "start_date": campaign.start_date.isoformat(),
        "end_date": campaign_end_date(campaign).isoformat(),
        "status": campaign.status,
        "source": campaign.source,
        "arcs": [
            {
                "id": arc.id,
                "index": arc.index,
                "name": arc.name,
                "weeks": arc.weeks,
                "run_miles_min": arc.run_miles_min,
                "run_miles_max": arc.run_miles_max,
                "long_run_miles": arc.long_run_miles,
                "deload_every_n_weeks": arc.deload_every_n_weeks,
                "deload_factor": arc.deload_factor,
                "notes": arc.notes,
                "start_date": a_start.isoformat(),
                "end_date": a_end.isoformat(),
                "templates": [
                    {
                        "id": t.id, "weekday": t.weekday, "type": t.type, "title": t.title,
                        "location_tag": t.location_tag, "load_hint": t.load_hint,
                        "items": list(t.items or []), "note": t.note,
                    }
                    for t in sorted(arc.templates, key=lambda t: t.weekday)
                ],
            }
            for arc, a_start, a_end in bounds
        ],
        "current_arc_index": ctx["arc_index"] if ctx else None,
        "week_in_arc": ctx["week_in_arc"] + 1 if ctx else None,
        "campaign_week": ctx["campaign_week"] if ctx else None,
        "deload_week": bool(ctx["deload"]) if ctx else False,
        "week_start": week_start.isoformat(),
        "week_target_miles": week_target_miles(db, campaign, week_start) if ctx else None,
        "overrides": dict(campaign.overrides or {}),
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }


def stored_system_line(hunt: PlannedHunt) -> str:
    """A System line from the persisted base prescription (week view, no fetch-time inputs)."""
    p = hunt.prescription or {}
    main = next((ex for ex in p.get("exercises", []) if ex.get("role") == "main"), None) \
        or (p.get("exercises") or [None])[0]
    if main is not None:
        top = next((s for s in reversed(main.get("sets", [])) if not s.get("is_warmup")), None)
        w = top.get("target_weight_lb") if top else None
        n = sum(1 for s in main.get("sets", []) if not s.get("is_warmup"))
        reps = f"{top['target_reps_lo']}" if top and top["target_reps_lo"] == top["target_reps_hi"] else (
            f"{top['target_reps_lo']}–{top['target_reps_hi']}" if top else "")
        head = f"{main.get('exercise_name', '').upper()} {n}×{reps}" + (f" @ {w:g}" if w else "")
        note = main.get("progression_note") or ""
        return f"[{note.split(' · ')[0]}] {head}" if note else head
    run = p.get("run")
    if run:
        return f"[{str(run.get('kind', 'run')).upper()} {float(run.get('miles', 0)):.1f} MI] HR ≤ {run.get('hr_cap_bpm')}"
    return f"[{(hunt.template.type if hunt.template else 'hunt').upper()}]"


def session_summary(session: Optional[WorkoutSession]) -> Optional[Dict[str, Any]]:
    if session is None:
        return None
    day = session_local_day(session)
    return {
        "id": session.id,
        "name": session.name,
        "local_date": day.isoformat() if day else None,
        "duration_minutes": session.duration_minutes,
        "total_sets": sum(len(we.sets) for we in (session.workout_exercises or [])),
        "distance_miles": session_miles(session) if session.distance_meters else None,
    }


def hunt_to_dict(
    hunt: PlannedHunt,
    *,
    prescription: Optional[Prescription] = None,
    session: Optional[WorkoutSession] = None,
) -> Dict[str, Any]:
    """§15.3 shape. With a live ``Prescription`` (today) or the stored base (week view)."""
    template = hunt.template
    if prescription is not None:
        body = prescription.to_dict()
        rationale = list(prescription.rationale)
        system_line = prescription.system_line
        modulation = prescription.modulation
        guard_flags = list(prescription.guard_flags)
        hunt_type = prescription.hunt_type
    else:
        body = copy.deepcopy(hunt.prescription) if hunt.prescription else None
        rationale = list(hunt.rationale or [])
        system_line = stored_system_line(hunt)
        modulation = None
        guard_flags = []
        hunt_type = template.type if template else HuntType.REST.value
    return {
        "id": hunt.id,
        "campaign_id": hunt.campaign_id,
        "arc_id": hunt.arc_id,
        "template_id": hunt.template_id,
        "date": hunt.date.isoformat(),
        "type": hunt_type,
        "title": template.title if template else "",
        "location_tag": template.location_tag if template else None,
        "status": hunt.status,
        "session_id": hunt.session_id,
        "moved_to": hunt.moved_to.isoformat() if hunt.moved_to else None,
        "prescription": body,
        "rationale": rationale,
        "system_line": system_line,
        "modulation": modulation,
        "guard_flags": guard_flags,
        "session_summary": session_summary(session),
    }


def pace_status(logged_miles: float, target_miles: Optional[float], week_start: date, today: date) -> str:
    """The PWA's verdict against a pro-rated target (≥1.2 ahead, ≥0.85 on pace)."""
    if not target_miles or target_miles <= 0:
        return "on_pace"
    if today < week_start:
        return "on_pace"
    day_idx = min(6, (today - week_start).days)
    expected = target_miles * (day_idx + 1) / 7
    if expected <= 0:
        return "on_pace"
    ratio = logged_miles / expected
    if ratio >= 1.2:
        return "ahead"
    if ratio >= 0.85:
        return "on_pace"
    return "behind"


def logged_run_miles(db: Session, user_id: str, week_start: date) -> float:
    """Run miles logged in the week (all run sessions, linked or not)."""
    week_end = week_start + timedelta(days=6)
    rows = (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSession.distance_meters.isnot(None),
            WorkoutSession.date >= datetime.combine(week_start - timedelta(days=1), datetime.min.time()),
            WorkoutSession.date < datetime.combine(week_end + timedelta(days=2), datetime.min.time()),
        )
        .all()
    )
    total = 0.0
    for s in rows:
        day = session_local_day(s)
        if day is None or day < week_start or day > week_end:
            continue
        if _is_run(s.activity_type) or (s.activity_type is None and s.distance_meters):
            total += session_miles(s)
    return round(total, 2)


__all__ = [
    "MATERIALIZE_AHEAD_DAYS",
    "XP_GUARD_RESPECTED",
    "XP_HUNT_DONE",
    "XP_HUNT_MODIFIED",
    "XP_WEEK_ON_PLAN",
    "append_guard_rationale",
    "apply_change_reps",
    "apply_deload_now",
    "apply_extend_arc",
    "apply_set_progression",
    "apply_set_week_miles",
    "apply_swap_days",
    "arc_weeks_from_label",
    "campaign_end_date",
    "campaign_to_dict",
    "create_campaign",
    "get_active_campaign",
    "get_campaign",
    "hunt_on",
    "hunt_to_dict",
    "import_campaign",
    "link_session_to_plan",
    "link_status",
    "logged_run_miles",
    "long_run_miles_for_week",
    "materialize_range",
    "monday_of",
    "move_hunt",
    "next_planned_hunt_with_family",
    "pace_status",
    "parse_day",
    "parse_item",
    "parse_phases",
    "parse_run_spec",
    "prescribe_and_store",
    "refresh_planned_hunts",
    "resolve_family",
    "retire_campaign",
    "session_kind",
    "skip_hunt",
    "swap_hunts",
    "template_families",
    "week_context",
    "week_target_miles",
]
