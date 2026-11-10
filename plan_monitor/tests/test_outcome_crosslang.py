"""Cross-language correctness of outcome parsing and test-run recognition.

Covers the two heuristics the finalization signals (stale_validation,
submission_after_reported_check_failure, no_successful_patch, ...) depend on:

  * ``buildGraph.check_command_outcome`` -- pass/fail from command output, across
    Python/JS/TS/Go/Rust/Java/Ruby/PHP/C#, precision-first;
  * ``mapLang._is_test_command``        -- recognizing a test/check run across
    languages, without misreading builds/lints as tests.

Plus the correctness guard that a str_replace_editor *view/edit* observation
(which echoes FILE CONTENT) is never scanned for pass/fail markers.
"""
from __future__ import annotations

import pytest

from plan_monitor.buildGraph import check_command_outcome, check_test_status
from plan_monitor.mapLang import _is_test_command, _cmd_base


# -- outcome: structured summaries are count-based (zero-count == pass) ---------

@pytest.mark.parametrize("obs, expected", [
    # pytest / python
    ("===== 0 failed, 12 passed in 1.2s =====", "success"),
    ("===== 3 failed, 9 passed in 1.2s =====", "failure"),
    ("0 errors, 5 passed", "success"),
    ("2 errors, 5 passed", "failure"),
    ("Ran 7 tests in 0.1s\n\nOK", "success"),
    ("Ran 7 tests in 0.1s\n\nFAILED (failures=1)", "failure"),
    ("Ran 7 tests in 0.1s\n\nFAILED (errors=2)", "failure"),
    ("Traceback (most recent call last):\n  File ...\nValueError", "failure"),
    # go
    ("ok  \texample.com/pkg\t0.42s", "success"),
    ("--- FAIL: TestThing (0.00s)\nFAIL\nexit status 1", "failure"),
    ("panic: runtime error: invalid memory address", "failure"),
    # rust / cargo
    ("test result: ok. 12 passed; 0 failed; 0 ignored", "success"),
    ("test result: FAILED. 10 passed; 2 failed; 0 ignored", "failure"),
    ("error[E0433]: failed to resolve: use of undeclared crate", "failure"),
    # js / ts: jest, vitest, mocha
    ("Tests:       1 failed, 2 passed, 3 total", "failure"),
    ("Tests:       0 failed, 3 passed, 3 total", "success"),
    ("Tests  5 passed | 0 failed (5)", "success"),
    ("Tests  2 failed | 3 passed (5)", "failure"),
    ("  12 passing (340ms)", "success"),
    ("  10 passing (340ms)\n  2 failing", "failure"),
    ("src/api/common/Env.ts:52:34 - error TS2304: Cannot find name 'env'.", "failure"),
    ("src/api/common/Env.ts(87,9): error TS2304: Cannot find name 'env'.", "failure"),
    # java / maven-surefire
    ("Tests run: 12, Failures: 0, Errors: 0, Skipped: 0", "success"),
    ("Tests run: 12, Failures: 2, Errors: 0, Skipped: 0", "failure"),
    ("Tests run: 12, Failures: 0, Errors: 1, Skipped: 0", "failure"),
    ("BUILD SUCCESS", "success"),
    ("BUILD FAILURE", "failure"),
    ("BUILD FAILED", "failure"),
    # ruby rspec
    ("5 examples, 0 failures", "success"),
    ("5 examples, 2 failures", "failure"),
    # php phpunit
    ("OK (12 tests, 30 assertions)", "success"),
    ("FAILURES!\nTests: 12, Assertions: 30, Failures: 2.", "failure"),
    # c# dotnet
    ("Passed!  - Failed:     0, Passed:    10, Skipped:     0", "success"),
    ("Failed!  - Failed:     2, Passed:     8, Skipped:     0", "failure"),
    # native crash, any language
    ("Segmentation fault (core dumped)", "failure"),
    # nothing recognized -> default success
    ("Done.", "success"),
    ("", "success"),
])
def test_check_command_outcome_crosslang(obs, expected):
    assert check_command_outcome("sometest", obs) == expected


def test_zero_count_is_never_failure():
    # the historical pytest zero-count false positive stays fixed across phrasings
    for obs in ("0 failed", "0 errors", "0 failing", "0 failures",
                "Failures: 0", "Errors: 0", "failures=0", "Failed: 0"):
        assert check_command_outcome("x", obs + " ; done") == "success"


def test_application_fail_message_is_not_a_framework_failure():
    # a repro script printing its own "FAIL:" lines while pytest passes must stay
    # a success -- a bare FAIL line is NOT a framework verdict (see mapLang note).
    obs = ("FAIL: %3A5 should not match\n"
           "FAIL: page01 should match\n"
           "===== 0 failed, 3 passed in 0.1s =====")
    assert check_command_outcome("python repro.py", obs) == "success"


# -- correctness: view/edit observations echo file CONTENT, never scan them ----

def test_str_replace_editor_view_is_not_outcome_scanned():
    # viewing a file whose CONTENT contains failure markers is still a success
    content = ("1\tdef f():\n2\t    raise ValueError  # Traceback (most recent call last):\n"
               "3\t    # error TS2304: ... and '3 failed' in a docstring")
    assert check_command_outcome("", content, tool="str_replace_editor", subcommand="view") == "success"


def test_successful_edit_snippet_is_not_outcome_scanned():
    # a successful str_replace echoes a `cat -n` snippet of the edited file; even if
    # that snippet contains "Traceback"/"3 failed", the EDIT succeeded.
    obs = ("The file /x.py has been edited. Here's the result of running `cat -n` on a snippet:\n"
           "  10\t    # Traceback (most recent call last): in the comment\n"
           "  11\t    assert out == '3 failed'")
    assert check_command_outcome("", obs, tool="str_replace_editor", subcommand="str_replace") == "success"


def test_failed_edit_is_still_failure():
    obs = "No replacement was performed, old_str did not appear verbatim in /x.py"
    assert check_command_outcome("", obs, tool="str_replace_editor", subcommand="str_replace") == "failure"


def test_unconfigured_editor_failed_edit_detected_by_prefix():
    # unconfigured parser: no subcommand; the failed edit is the leading tool message
    obs = "No replacement was performed, old_str `def f` did not appear verbatim in /x.py"
    assert check_command_outcome("str_replace_editor", obs) == "failure"


def test_unconfigured_editor_view_quoting_failure_phrase_is_success():
    # viewing source that merely CONTAINS the failure phrase (e.g. this very module)
    # must NOT be read as a failed edit -- the phrase is file content, not a prefix.
    obs = ("Here's the result of running `cat -n` on /repo/buildGraph.py:\n"
           "  33\t        if \"did not appear verbatim\" in obs:\n"
           "  34\t            return \"failure: not found\"")
    assert check_command_outcome("str_replace_editor", obs) == "success"


# -- check_test_status back-compat shim shares the same core -------------------

def test_check_test_status_only_for_test_heads():
    assert check_test_status("ls", "3 failed") is None          # not a test head
    assert check_test_status("pytest", "3 failed, 1 passed") == "failure"
    assert check_test_status("pytest", "0 failed, 1 passed") == "success"


# -- run_test recognition across languages ------------------------------------

@pytest.mark.parametrize("cmd, tokens, expected", [
    # direct runners
    ("pytest", ["-q"], True),
    ("jest", ["--coverage"], True),
    ("vitest", ["run"], True),
    ("rspec", ["spec/"], True),
    ("mocha", ["test/"], True),
    ("phpunit", ["--filter", "x"], True),
    ("ginkgo", ["./..."], True),
    ("bats", ["test.bats"], True),
    # host + test sub-token
    ("go", ["test", "./..."], True),
    ("cargo", ["test"], True),
    ("cargo", ["nextest", "run"], True),
    ("npm", ["test"], True),
    ("npm", ["t"], True),
    ("yarn", ["test"], True),
    ("pnpm", ["test"], True),
    ("bun", ["test"], True),
    ("deno", ["test"], True),
    ("dotnet", ["test"], True),
    ("mvn", ["verify"], True),
    ("gradle", ["check"], True),
    ("make", ["check"], True),
    ("make", ["test"], True),
    ("rake", ["spec"], True),
    ("mix", ["test"], True),
    ("swift", ["test"], True),
    # path-prefixed hosts
    ("./gradlew", ["test"], True),
    ("/usr/bin/go", ["test"], True),
    # launchers delegating to a runner
    ("npx", ["jest"], True),
    ("poetry", ["run", "pytest"], True),
    ("bundle", ["exec", "rspec"], True),
    ("uv", ["run", "pytest"], True),
    # NON-tests: builds, lints, runs
    ("go", ["build", "./..."], False),
    ("npm", ["run", "lint"], False),
    ("gradle", ["build"], False),
    ("make", ["all"], False),
    ("cargo", ["build"], False),
    ("ls", ["-la"], False),
    ("git", ["status"], False),
    ("node", ["server.js"], False),
])
def test_is_test_command_crosslang(cmd, tokens, expected):
    assert _is_test_command(cmd, tokens) is expected


def test_cmd_base_normalization():
    assert _cmd_base("./gradlew") == "gradlew"
    assert _cmd_base("/usr/bin/go") == "go"
    assert _cmd_base("bin/pytest") == "pytest"
    assert _cmd_base("pytest") == "pytest"
