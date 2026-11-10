"""
Replay correctness invariants (REPLAY_PROTOCOL §2 + IMPLEMENTATION §6):

  * No future leakage: a signal's verdict is independent of ITS OWN recorded
    observation (q's observation is never read at propose).
  * Historical observations DO matter: flipping an earlier edit's recorded result
    legitimately changes a later submission verdict.
  * Unconditional commit after a hypothetical block: a block-worthy action is still
    present in the next prefix (it is not rolled back).
  * Submits are opportunities, not ranked or counted (online semantics).
  * End-to-end pipeline wiring: a crafted failure fires the right signal.

Detection is read from the per-run, per-signal rollup (``meta["signals"]``) — the
replay's single detection record. ``n_true > 0`` means the signal fired.
"""
from analysis.replay.replay_monitor import replay_trajectory, submit_gated_signals
from analysis.pattern_resolution.sources import replay_detail
from plan_monitor.gl_guard.guard_monitor import GuardMonitor
from plan_monitor.gl_guard.model import Hook


def _stat(out, signal):
    return (out["meta"]["signals"] or {}).get(signal, {})


def _fired(out, signal):
    return _stat(out, signal).get("n_true", 0) > 0


def test_no_future_leakage_on_submit_observation(make_traj):
    base = [
        ("str_replace_editor view /testbed/pkg/mod.py", "class Foo: pass"),
        ("str_replace_editor str_replace /testbed/pkg/mod.py", "The file has been edited."),
        ("python /testbed/reproduce.py", "12 passed"),
        ("submit", "SUBMIT-OBS-A"),
    ]
    variant = list(base)
    variant[-1] = ("submit", "completely different submit observation XYZ 3 failed")
    out_a = replay_trajectory(make_traj(base))
    out_b = replay_trajectory(make_traj(variant))
    # The whole detection rollup must be identical: q's own observation (success vs a
    # '3 failed' string) cannot influence its propose verdict, and nothing runs after.
    assert out_a["meta"]["signals"] == out_b["meta"]["signals"]


def test_historical_observation_changes_later_verdict(make_traj):
    # Same actions; only the EDIT's recorded result differs. With the edit failing,
    # no successful patch exists -> no_successful_patch fires at submit; with it
    # succeeding, it does not. This proves committed-history evidence is used.
    fail = [
        ("str_replace_editor view /testbed/pkg/mod.py", "src"),
        ("str_replace_editor str_replace /testbed/pkg/mod.py", "did not appear verbatim"),
        ("submit", ""),
    ]
    ok = list(fail)
    ok[1] = ("str_replace_editor str_replace /testbed/pkg/mod.py", "The file has been edited.")
    assert _fired(replay_trajectory(make_traj(fail)), "no_successful_patch")
    assert not _fired(replay_trajectory(make_traj(ok)), "no_successful_patch")


def test_unconditional_commit_after_hypothetical_block(make_traj):
    # Step 1 edits before any localization -> premature_patch BLOCKS in the live
    # monitor. The replay must NOT roll it back: at submit, the patch is in history
    # (skip_patch is FALSE). A rollback would drop the edit and skip_patch would fire.
    steps = [
        ("str_replace_editor str_replace /testbed/pkg/mod.py", "The file has been edited."),
        ("submit", ""),
    ]
    out = replay_trajectory(make_traj(steps))
    assert not _fired(out, "plan_compliance_skip_patch")
    assert out["meta"]["n_steps"] == 2          # the edit was committed, not rolled back


def test_end_to_end_no_successful_patch_fires(make_traj):
    steps = [
        ("str_replace_editor view /testbed/pkg/mod.py", "src"),
        ("str_replace_editor str_replace /testbed/pkg/mod.py", "did not appear verbatim"),
        ("submit", ""),
    ]
    out = replay_trajectory(make_traj(steps))
    assert _fired(out, "no_successful_patch")
    # the emission policy would surface AND block this shadow (disabled) signal
    st = _stat(out, "no_successful_patch")
    assert st.get("n_emit", 0) >= 1
    assert st.get("n_block", 0) >= 1            # blocking-configured


def test_submits_are_opportunities_not_ranked_or_counted(make_traj):
    # Online semantics: each submit proposal is evaluated on its own. A review-on-submit
    # scaffold may bounce the first submit and make the agent submit again; the replay
    # does not rank, count, or distinguish submits — it only records that the run
    # submitted (the opportunity) and what each signal did.
    steps = [
        ("str_replace_editor str_replace /testbed/pkg/mod.py", "The file has been edited."),
        ("submit", "anything at all -- wording is irrelevant"),
        ("rm /testbed/reproduce.py", ""),
        ("submit", ""),
    ]
    out = replay_trajectory(make_traj(steps))
    meta = out["meta"]
    assert meta["submitted"] is True
    assert "rows" not in out                     # no per-submit ledger
    for absent in ("n_submits", "n_dispatch_submits", "dispatch_submit_step"):
        assert absent not in meta                # submits are not ranked or counted


def test_run_without_submit_is_not_marked_submitted(make_traj):
    steps = [("str_replace_editor view /testbed/pkg/mod.py", "class Foo: pass")]
    out = replay_trajectory(make_traj(steps))
    assert out["meta"]["submitted"] is False     # no opportunity for submission signals


def test_compound_nonlast_outcome_is_unknown_not_faked(make_traj):
    # A committed compound step 'python reproduce.py && echo done': the single
    # observation belongs to the last sub-command (echo). The non-last sub-command
    # (python) must carry an UNKNOWN outcome, never a faked 'success' -- pending /
    # un-observed compound sub-commands do not enter committed history as successes.
    from plan_monitor.gl_guard.guard_monitor import GuardMonitor
    from plan_monitor.phases import ActionEvent
    mon = GuardMonitor(); mon.reset()
    ev = ActionEvent(step_index=1, command="python reproduce.py && echo done")
    mon.check_step_pre_emptively(ev, thought="")
    mon.observe_result("3 failed, 1 passed")     # real result, attributed to echo (last)
    outs = {d.get("command"): d.get("outcome") for _, d in mon.graph_builder.G.nodes(data=True)}
    assert outs.get("python") == [None]          # non-last: honest unknown
    assert outs.get("echo") == ["failure"]       # last: got the observation


def test_malformed_trajectory_is_reported_not_raised(tmp_path):
    bad = tmp_path / "bad.traj"
    bad.write_text("{ not json")
    out = replay_trajectory(str(bad))
    assert "error" in out["meta"]
    assert out["meta"]["n_steps"] == 0


# -- thought-only steps are replayed; thought_oscillation is exercised ----------

def test_thought_only_steps_feed_thought_oscillation(make_traj):
    # Three identical thought-only steps (no action) -> m_thought=1 repeated
    # r_thought=3 -> thought_oscillation fires, exactly as online. The extractor now
    # surfaces thought-only steps to the replay (include_thought_steps=True).
    steps = [
        ("", "", "I will look at the failing module first."),   # thought-only
        ("", "", "I will look at the failing module first."),   # identical
        ("", "", "I will look at the failing module first."),   # identical -> 3x
    ]
    out = replay_trajectory(make_traj(steps))
    assert out["meta"]["n_thought_steps"] == 3
    assert out["meta"]["n_steps"] == 0                          # no action steps
    assert out["meta"]["signals"]["thought_oscillation"]["n_true"] >= 1


def test_distinct_thoughts_do_not_oscillate(make_traj):
    steps = [
        ("", "", "First, reproduce the bug."),
        ("", "", "Now localize the faulty function."),
        ("", "", "Finally, write the fix."),
    ]
    out = replay_trajectory(make_traj(steps))
    assert out["meta"]["n_thought_steps"] == 3
    to = out["meta"]["signals"].get("thought_oscillation", {})
    assert to.get("n_true", 0) == 0


def test_action_steps_reset_the_reasoning_episode_counts(make_traj):
    # Thought-only steps interleaved with an action still accumulate into the
    # thought stream; the run is replayed end-to-end without error and both step
    # kinds are counted.
    steps = [
        ("", "", "thinking about the plan"),
        ("str_replace_editor view /testbed/pkg/mod.py", "class Foo: pass"),
        ("", "", "thinking about the plan"),
        ("submit", "diff --git a/x b/x"),
    ]
    out = replay_trajectory(make_traj(steps))
    assert out["meta"]["n_thought_steps"] == 2
    assert out["meta"]["n_steps"] == 2          # view + submit
    assert out["meta"]["submitted"] is True


# -- submit-gated signals are scored at the FINAL submit (offline rollup) --------

def test_submit_gated_signals_detected_structurally():
    # The plan-compliance skip_* family REQUIRES kind(q)=submit and so is submit-gated;
    # oscillation / action_recurrence say `not kind(q)=submit` and must NOT be.
    mon = GuardMonitor(); mon.reset()
    gated = submit_gated_signals(mon.runtime.program, Hook.PROPOSE)
    assert {"plan_compliance_skip_patch", "plan_compliance_skip_validation"} <= gated
    assert "oscillation" not in gated          # negated occurrence, not a submit signal
    assert "action_recurrence" not in gated
    assert "dwell_P" not in gated              # not submit-conditioned at all


def test_replay_detail_reads_final_submit_not_first(make_traj):
    # A premature submit (no patch yet) followed by a real patch + validation + a
    # proper submit. The ONLINE engine fires skip_patch/skip_validation at the first
    # (premature) submit -- correctly, that attempt warranted a block -- so the raw
    # per-step rollup (replay_trajectory) records n_true > 0. But the completed
    # trajectory ended patched + validated, so replay_detail (which scores submit-
    # gated signals at the FINAL submit) must report them FALSE. This is exactly the
    # refiner case where a blocked-then-corrected attempt was being miscounted.
    steps = [
        ("str_replace_editor view /testbed/pkg/mod.py", "class Foo: pass"),  # localize
        ("submit", ""),                                                       # premature submit #1
        ("str_replace_editor str_replace /testbed/pkg/mod.py", "The file has been edited."),  # patch
        ("python -m pytest /testbed/tests/test_mod.py", "1 passed"),          # validate
        ("submit", ""),                                                       # proper final submit
    ]
    traj = make_traj(steps)
    # The raw per-step ledger shows the signals DID fire (at the premature attempt).
    raw = replay_trajectory(traj)
    assert _fired(raw, "plan_compliance_skip_patch")
    # The completed-trajectory detail reads the final submit -> not a violation.
    detail = replay_detail(traj)
    assert detail["signals"]["plan_compliance_skip_patch"] is False
    assert detail["signals"]["plan_compliance_skip_validation"] is False
    # A non-submit signal is unaffected (still "fired at any step").
    assert "P" in detail["unique_phases"].split(",")  # the patch was seen


def test_replay_detail_keeps_violation_when_final_submit_is_bad(make_traj):
    # Guard against over-correction: a run that NEVER patches must still report the
    # skip_patch violation at its (only) submit -- the final-submit rule changes
    # which submit is read, not whether a genuine terminal violation is reported.
    steps = [
        ("str_replace_editor view /testbed/pkg/mod.py", "class Foo: pass"),
        ("submit", ""),
    ]
    detail = replay_detail(make_traj(steps))
    assert detail["signals"]["plan_compliance_skip_patch"] is True
