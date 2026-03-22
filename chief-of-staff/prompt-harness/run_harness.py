#!/usr/bin/env python3
"""Action item extraction prompt harness.

Runs the two-tier extraction pipeline (Haiku triage + Sonnet extraction)
against the test corpus and scores precision/recall.

Usage:
    python run_harness.py                  # Run all fixtures
    python run_harness.py --source gmail   # Only Gmail fixtures
    python run_harness.py --id commit_01   # Single fixture
    python run_harness.py --verbose        # Show per-fixture details
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from prompts import (
    TRIAGE_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    format_triage_prompt,
    format_extraction_prompt,
    preprocess_body,
)
from test_corpus import get_fixtures, get_fixture_by_id


# =============================================================================
# MODELS
# =============================================================================

T = TypeVar("T", bound=BaseModel)


class TriageResult(BaseModel):
    has_action_items: bool
    reasoning: str = ""


class ExtractedItem(BaseModel):
    title: str
    description: str = ""
    people: list[str] = []
    deadline: str | None = None
    confidence: float = 0.0
    priority: str = "medium"
    commitment_type: str = "they_requested"


class ExtractionResult(BaseModel):
    action_items: list[ExtractedItem] = []


class FixtureResult(BaseModel):
    fixture_id: str
    source: str
    subject: str
    triage_expected: bool
    triage_actual: bool | None = None
    triage_correct: bool | None = None
    triage_reasoning: str = ""
    expected_count: int
    extracted_count: int = 0
    expected_items: list[dict] = []
    extracted_items: list[dict] = []
    matched_items: int = 0
    false_positives: int = 0
    missed_items: int = 0
    error: str | None = None
    triage_cost: float = 0.0
    extraction_cost: float = 0.0


# =============================================================================
# API CALLS
# =============================================================================

# Pricing per 1M tokens (verified March 2026)
PRICING = {
    "haiku": {"input": 0.80, "output": 4.00},
    "sonnet": {"input": 3.00, "output": 15.00},
}

TRIAGE_MODEL = "claude-haiku-4-5-20251001"
EXTRACTION_MODEL = "claude-sonnet-4-6"

# Match nested JSON objects (handles one level of nesting)
_RE_JSON_OBJECT = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate API cost in dollars."""
    tier = "haiku" if "haiku" in model else "sonnet"
    prices = PRICING[tier]
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


def _extract_json(text: str) -> dict:
    """Extract JSON object from API response, handling code blocks and preamble."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Find first JSON object (handles one level of nesting)
    match = _RE_JSON_OBJECT.search(text)
    if match:
        return json.loads(match.group(0))

    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


def _call_api(
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    result_cls: type[T],
) -> tuple[T, float]:
    """Call Claude API, parse JSON response, return (typed result, cost)."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if not response.content:
        raise ValueError("Empty response from API")

    data = _extract_json(response.content[0].text.strip())
    result = result_cls(**data)
    cost = _estimate_cost(response.usage.input_tokens, response.usage.output_tokens, model)
    return result, cost


# =============================================================================
# MATCHING / SCORING
# =============================================================================

_RE_NON_WORD = re.compile(r"[^\w]")
_STOP_WORDS = {"the", "a", "an", "to", "for", "and", "or", "with", "on", "in", "of", "by", "is", "it"}


def fuzzy_title_match(expected: str, actual: str) -> bool:
    """Check if two action item titles are roughly about the same thing.

    Requires at least 2 matching significant words and 50%+ overlap.
    """
    def significant_words(text: str) -> set[str]:
        return {_RE_NON_WORD.sub("", w.lower()) for w in text.split()} - _STOP_WORDS - {""}

    expected_words = significant_words(expected)
    actual_words = significant_words(actual)

    if not expected_words:
        return False

    overlap = len(expected_words & actual_words)
    return overlap >= 2 and overlap / len(expected_words) >= 0.4


def score_fixture(fixture: dict, extracted: list[ExtractedItem]) -> tuple[int, int, int]:
    """Score extraction results against expected items.

    Returns (matched, false_positives, missed).
    """
    expected = fixture["expected_action_items"]
    matched = 0
    used_extracted: set[int] = set()

    for exp in expected:
        for i, ext in enumerate(extracted):
            if i in used_extracted:
                continue
            if fuzzy_title_match(exp["title"], ext.title):
                matched += 1
                used_extracted.add(i)
                break

    false_positives = len(extracted) - len(used_extracted)
    missed = len(expected) - matched
    return matched, false_positives, missed


# =============================================================================
# MAIN HARNESS
# =============================================================================


def run_fixture(
    client: anthropic.Anthropic, fixture: dict, verbose: bool = False
) -> FixtureResult:
    """Run the full triage + extraction pipeline on a single fixture."""
    result = FixtureResult(
        fixture_id=fixture["id"],
        source=fixture["source"],
        subject=fixture["subject"],
        triage_expected=fixture["expected_has_action_items"],
        expected_count=len(fixture["expected_action_items"]),
        expected_items=fixture["expected_action_items"],
    )

    # Preprocess once — shared between triage and extraction
    body = preprocess_body(fixture["raw_text"])

    try:
        triage, triage_cost = _call_api(
            client, TRIAGE_MODEL, 200, TRIAGE_SYSTEM_PROMPT,
            format_triage_prompt(fixture, preprocessed_body=body),
            TriageResult,
        )
        result.triage_actual = triage.has_action_items
        result.triage_correct = triage.has_action_items == fixture["expected_has_action_items"]
        result.triage_reasoning = triage.reasoning
        result.triage_cost = triage_cost

        if verbose:
            status = "PASS" if result.triage_correct else "FAIL"
            print(f"  Triage [{status}]: expected={fixture['expected_has_action_items']}, "
                  f"got={triage.has_action_items} — {triage.reasoning}")

        if triage.has_action_items:
            extraction, extraction_cost = _call_api(
                client, EXTRACTION_MODEL, 2000, EXTRACTION_SYSTEM_PROMPT,
                format_extraction_prompt(fixture, preprocessed_body=body),
                ExtractionResult,
            )
            result.extracted_count = len(extraction.action_items)
            result.extracted_items = [item.model_dump() for item in extraction.action_items]
            result.extraction_cost = extraction_cost

            matched, fp, missed = score_fixture(fixture, extraction.action_items)
            result.matched_items = matched
            result.false_positives = fp
            result.missed_items = missed

            if verbose:
                for item in extraction.action_items:
                    print(f"    -> {item.title} (conf={item.confidence:.1f}, pri={item.priority})")
                print(f"  Score: {matched} matched, {fp} false positives, {missed} missed")
        elif fixture["expected_has_action_items"]:
            result.missed_items = len(fixture["expected_action_items"])

    except (anthropic.RateLimitError, anthropic.AuthenticationError):
        raise
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        result.error = f"{type(e).__name__}: {e}"
        if verbose:
            print(f"  ERROR: {result.error}")
    except anthropic.APIError as e:
        result.error = f"API error: {e}"
        if verbose:
            print(f"  ERROR: {result.error}")

    return result


def print_scorecard(results: list[FixtureResult]) -> dict:
    """Print a summary scorecard and return metrics."""
    print("\n" + "=" * 70)
    print("SCORECARD")
    print("=" * 70)

    ok_results = [r for r in results if r.error is None]
    errored = len(results) - len(ok_results)
    if errored:
        print(f"\n({errored} fixture(s) errored — excluded from scoring)")

    # Triage metrics — single pass
    triage_tp = triage_fp = triage_fn = triage_tn = 0
    for r in ok_results:
        if r.triage_actual is None:
            continue
        if r.triage_expected and r.triage_actual:
            triage_tp += 1
        elif not r.triage_expected and r.triage_actual:
            triage_fp += 1
        elif r.triage_expected and not r.triage_actual:
            triage_fn += 1
        else:
            triage_tn += 1

    triage_total = triage_tp + triage_fp + triage_fn + triage_tn
    triage_correct = triage_tp + triage_tn
    triage_precision = triage_tp / (triage_tp + triage_fp) if (triage_tp + triage_fp) > 0 else 0
    triage_recall = triage_tp / (triage_tp + triage_fn) if (triage_tp + triage_fn) > 0 else 0

    print(f"\n--- Triage (Haiku) ---")
    pct = triage_correct / triage_total * 100 if triage_total > 0 else 0
    print(f"Accuracy:  {triage_correct}/{triage_total} ({pct:.0f}%)")
    print(f"Precision: {triage_precision:.1%} (TP={triage_tp}, FP={triage_fp})")
    print(f"Recall:    {triage_recall:.1%} (TP={triage_tp}, FN={triage_fn})")
    print(f"True Neg:  {triage_tn}")

    # Extraction metrics
    total_expected = sum(r.expected_count for r in ok_results if r.triage_expected)
    total_matched = sum(r.matched_items for r in ok_results)
    total_fp = sum(r.false_positives for r in ok_results)
    total_missed = sum(r.missed_items for r in ok_results)

    ext_precision = total_matched / (total_matched + total_fp) if (total_matched + total_fp) > 0 else 0
    ext_recall = total_matched / (total_matched + total_missed) if (total_matched + total_missed) > 0 else 0
    fp_rate = total_fp / (total_matched + total_fp) if (total_matched + total_fp) > 0 else 0

    print(f"\n--- Extraction (Sonnet) ---")
    print(f"Expected items:  {total_expected}")
    print(f"Matched:         {total_matched}")
    print(f"False positives: {total_fp}")
    print(f"Missed:          {total_missed}")
    print(f"Precision:       {ext_precision:.1%}")
    print(f"Recall:          {ext_recall:.1%}")
    print(f"FP Rate:         {fp_rate:.1%}")

    # Cost
    total_triage_cost = sum(r.triage_cost for r in results)
    total_extraction_cost = sum(r.extraction_cost for r in results)
    total_cost = total_triage_cost + total_extraction_cost

    print(f"\n--- Cost ---")
    print(f"Triage (Haiku):     ${total_triage_cost:.4f}")
    print(f"Extraction (Sonnet): ${total_extraction_cost:.4f}")
    print(f"Total:              ${total_cost:.4f}")

    # Thresholds
    print(f"\n--- Threshold Check ---")
    thresholds = {
        "Triage precision > 90%": triage_precision > 0.90,
        "Extraction recall > 80%": ext_recall > 0.80,
        "FP rate < 15%": fp_rate < 0.15,
    }
    all_pass = True
    for name, passed in thresholds.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    print(f"\nOverall: {'ALL THRESHOLDS MET' if all_pass else 'THRESHOLDS NOT MET'}")

    errors = [r for r in results if r.error]
    if errors:
        print(f"\n--- Errors ({len(errors)}) ---")
        for r in errors:
            print(f"  {r.fixture_id}: {r.error}")

    return {
        "triage_accuracy": triage_correct / triage_total if triage_total > 0 else 0,
        "triage_precision": triage_precision,
        "triage_recall": triage_recall,
        "extraction_precision": ext_precision,
        "extraction_recall": ext_recall,
        "false_positive_rate": fp_rate,
        "total_cost": total_cost,
        "all_thresholds_met": all_pass,
    }


def save_results(results: list[FixtureResult], metrics: dict) -> Path:
    """Save results to a timestamped JSON file."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = results_dir / f"run_{timestamp}.json"

    output = {
        "timestamp": timestamp,
        "fixture_count": len(results),
        "metrics": metrics,
        "results": [r.model_dump() for r in results],
    }

    output_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults saved to: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Action item extraction prompt harness")
    parser.add_argument("--source", choices=["gmail", "github", "slack"], help="Filter by source")
    parser.add_argument("--id", help="Run a single fixture by ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-fixture details")
    parser.add_argument("--dry-run", action="store_true", help="Show fixtures without calling API")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    if args.id:
        fixture = get_fixture_by_id(args.id)
        if not fixture:
            print(f"Error: fixture '{args.id}' not found")
            sys.exit(1)
        fixtures = [fixture]
    else:
        fixtures = get_fixtures(source=args.source)

    print(f"Running harness on {len(fixtures)} fixtures...")
    if args.source:
        print(f"  Filter: source={args.source}")

    if args.dry_run:
        for f in fixtures:
            has = "ACTION" if f["expected_has_action_items"] else "NO_ACTION"
            count = len(f["expected_action_items"])
            print(f"  [{has}] {f['id']} ({f['source']}) — {f['subject']} — {count} expected items")
        return

    client = anthropic.Anthropic()
    results: list[FixtureResult] = []

    for i, fixture in enumerate(fixtures, 1):
        print(f"\n[{i}/{len(fixtures)}] {fixture['id']} — {fixture['subject']}")
        result = run_fixture(client, fixture, verbose=args.verbose)
        results.append(result)
        if i < len(fixtures):
            time.sleep(0.5)

    metrics = print_scorecard(results)
    save_results(results, metrics)


if __name__ == "__main__":
    main()
