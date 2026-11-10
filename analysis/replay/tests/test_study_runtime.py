"""The replay's shadow-augmented runtime: completeness + overlap-safety.

``build_study_runtime`` merges the live ``liveplan.glg`` profile with the shadow
candidate specs (``extra_signals.glg``). It must include both sets and must stay
well-formed — and correct — even when a signal name appears in more than one spec
(the live definition wins; the duplicate is dropped, never crashing the checker).
"""
from analysis.replay.replay_monitor import DEFAULT_SHADOW_SPECS, build_study_runtime


def _names(rt):
    return [r.name for r in rt.program.rules]


def test_default_merge_is_complete_and_unique():
    names = _names(build_study_runtime())
    assert len(names) == len(set(names)), "no duplicate signals in the merged program"
    # live baseline present...
    assert {"oscillation", "repeated_view", "thought_oscillation",
            "plan_compliance_skip_patch"} <= set(names)
    # ...and the shadow candidates present (evaluated under include_disabled).
    assert {"no_successful_patch",
            "submission_after_reported_check_failure"} <= set(names)


def test_empty_shadow_specs_is_live_profile_only():
    live = _names(build_study_runtime(shadow_specs=()))
    assert "no_successful_patch" not in live     # candidate not merged
    assert "plan_compliance_skip_patch" in live                  # live signal present
    assert len(live) == len(set(live))


def test_overlapping_specs_are_deduped_live_wins():
    # Feed the live spec itself in AS a shadow spec: every name then overlaps the
    # base. The merge must drop the duplicates (live definition wins), not raise a
    # duplicate-name error, and the result must equal the live-only program.
    live = _names(build_study_runtime(shadow_specs=()))
    overlap = _names(build_study_runtime(
        shadow_specs=(("liveplan.glg", "liveplan.advice.json"),)))
    assert overlap == live
    assert len(overlap) == len(set(overlap))

    # Listing the same candidate spec twice is likewise idempotent.
    once = _names(build_study_runtime(shadow_specs=DEFAULT_SHADOW_SPECS))
    twice = _names(build_study_runtime(shadow_specs=DEFAULT_SHADOW_SPECS * 2))
    assert twice == once
    # advice entries are not duplicated either (dict-merge, live wins)
    rt = build_study_runtime(shadow_specs=DEFAULT_SHADOW_SPECS * 2)
    assert len(rt.registry.entries) == len(set(rt.registry.entries))
