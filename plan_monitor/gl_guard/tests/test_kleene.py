"""Unit tests for the strong-Kleene logic core."""
from __future__ import annotations

import itertools

import pytest

from plan_monitor.gl_guard.kleene import F, T, U, from_bool, k_and, k_not, k_or

ALL = [T, F, U]


def test_not():
    assert k_not(T) is F
    assert k_not(F) is T
    assert k_not(U) is U


def test_and_truth_table():
    assert k_and(T, T) is T
    assert k_and(T, F) is F
    assert k_and(F, U) is F   # F dominates even over ?
    assert k_and(T, U) is U
    assert k_and(U, U) is U


def test_or_truth_table():
    assert k_or(F, F) is F
    assert k_or(T, F) is T
    assert k_or(T, U) is T    # T dominates even over ?
    assert k_or(F, U) is U
    assert k_or(U, U) is U


def test_nary_and_empty_is_true_identity():
    assert k_and() is T
    assert k_or() is F


def test_de_morgan_holds_in_kleene():
    for a, b in itertools.product(ALL, repeat=2):
        assert k_not(k_and(a, b)) is k_or(k_not(a), k_not(b))
        assert k_not(k_or(a, b)) is k_and(k_not(a), k_not(b))


def test_no_bool_coercion():
    with pytest.raises(TypeError):
        bool(U)


def test_from_bool():
    assert from_bool(True) is T
    assert from_bool(False) is F
