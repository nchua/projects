"""Mechanical checks: code, not models (SPEC §6.3, §6.4).

Every check returns ``CheckResult`` objects; the stage hands them to the runner,
which records all of them and turns failures into flags. Nothing here raises
on bad content, so an over-long recap is a flag the editor fixes, not a crash.
"""
