"""Tests for app/ai_policy.py – pure logic, no Azure required."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import pytest

from app.ai_policy import should_call_ai, PolicyDecision


# ---------------------------------------------------------------------------
# Minimal Config stub (no Azure, no I/O)
# ---------------------------------------------------------------------------

@dataclass
class _Config:
    enable_ai: bool = False
    ai_provider: str = "none"
    ai_max_calls_per_run: int = 20
    ai_min_confidence_threshold: int = 60
    ai_policy_mode: str = "conservative"


def _make_config(**overrides: Any) -> _Config:
    cfg = _Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _call(
    rule_class: str = "unknown",
    rule_confidence: int = 30,
    reason_code: str = "no_rule_match",
    extension: str = ".docx",
    config: _Config = None,
    ai_calls_used: int = 0,
    mode: str = "classify",
    dry_run: bool = False,
) -> PolicyDecision:
    if config is None:
        config = _make_config(enable_ai=True, ai_provider="foundry")
    return should_call_ai(
        rule_class=rule_class,
        rule_confidence=rule_confidence,
        reason_code=reason_code,
        extension=extension,
        config=config,
        ai_calls_used=ai_calls_used,
        mode=mode,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Hard gates
# ---------------------------------------------------------------------------

class TestHardGates:
    def test_ai_disabled_returns_false(self):
        cfg = _make_config(enable_ai=False, ai_provider="foundry")
        d = _call(config=cfg)
        assert not d.should_call
        assert d.skip_reason == "ai_disabled"

    def test_provider_none_returns_false(self):
        cfg = _make_config(enable_ai=True, ai_provider="none")
        d = _call(config=cfg)
        assert not d.should_call
        assert d.skip_reason == "ai_provider_none"

    def test_wrong_mode_scan_returns_false(self):
        cfg = _make_config(enable_ai=True, ai_provider="foundry")
        d = _call(config=cfg, mode="scan")
        assert not d.should_call
        assert "wrong_mode" in d.skip_reason

    def test_dry_run_returns_false(self):
        cfg = _make_config(enable_ai=True, ai_provider="foundry")
        d = _call(config=cfg, dry_run=True)
        assert not d.should_call
        assert d.skip_reason == "dry_run"

    def test_budget_exhausted_still_marks_candidate(self):
        cfg = _make_config(enable_ai=True, ai_provider="foundry", ai_max_calls_per_run=5)
        d = _call(config=cfg, ai_calls_used=5)
        assert not d.should_call
        assert d.skip_reason == "budget_exhausted"
        assert d.is_ai_candidate  # still a candidate, just skipped

    def test_budget_not_yet_exhausted_allows_call(self):
        cfg = _make_config(enable_ai=True, ai_provider="foundry", ai_max_calls_per_run=5)
        d = _call(config=cfg, ai_calls_used=4)
        assert d.should_call


# ---------------------------------------------------------------------------
# Candidate detection
# ---------------------------------------------------------------------------

class TestCandidateDetection:
    def test_class_unknown_is_candidate(self):
        d = _call(rule_class="unknown", rule_confidence=30)
        assert d.should_call
        assert d.is_ai_candidate

    def test_no_rule_match_is_candidate(self):
        d = _call(rule_class="unknown", reason_code="no_rule_match", rule_confidence=30)
        assert d.should_call
        assert d.is_ai_candidate

    def test_low_confidence_below_60_is_candidate(self):
        d = _call(rule_class="finance", rule_confidence=55)
        assert d.should_call
        assert d.is_ai_candidate

    def test_strong_br_rule_is_not_candidate(self):
        # br threshold is 90 – confidence 90 → not a candidate
        d = _call(rule_class="br", rule_confidence=90, reason_code="path_rule_br")
        assert not d.should_call
        assert not d.is_ai_candidate

    def test_weak_br_rule_is_candidate(self):
        # br threshold is 90 – confidence 85 → candidate
        d = _call(rule_class="br", rule_confidence=85, reason_code="path_rule_br")
        assert d.should_call
        assert d.is_ai_candidate

    def test_strong_dsgvo_rule_is_not_candidate(self):
        d = _call(rule_class="dsgvo", rule_confidence=85, reason_code="keyword_dsgvo")
        assert not d.should_call

    def test_strong_technical_rule_is_not_candidate(self):
        d = _call(rule_class="technical", rule_confidence=70, reason_code="ext_technical")
        assert not d.should_call

    def test_strong_hr_rule_is_not_candidate(self):
        d = _call(rule_class="hr", rule_confidence=80, reason_code="path_rule_hr")
        assert not d.should_call

    def test_strong_finance_rule_is_not_candidate(self):
        d = _call(rule_class="finance", rule_confidence=80, reason_code="path_rule_finance")
        assert not d.should_call

    def test_strong_contract_rule_is_not_candidate(self):
        d = _call(rule_class="contract", rule_confidence=75, reason_code="keyword_contract")
        assert not d.should_call


# ---------------------------------------------------------------------------
# Extension blocking
# ---------------------------------------------------------------------------

class TestExtensionBlocking:
    def test_exe_blocked(self):
        d = _call(extension=".exe")
        assert not d.should_call
        assert "blocked_extension" in d.skip_reason
        assert d.is_ai_candidate  # still a candidate (by class/conf), just skipped

    def test_mp4_blocked(self):
        d = _call(extension=".mp4")
        assert not d.should_call

    def test_jpg_blocked(self):
        d = _call(extension=".jpg")
        assert not d.should_call

    def test_docx_allowed(self):
        d = _call(extension=".docx")
        assert d.should_call

    def test_pdf_allowed(self):
        d = _call(extension=".pdf")
        assert d.should_call

    def test_txt_allowed(self):
        d = _call(extension=".txt")
        assert d.should_call


# ---------------------------------------------------------------------------
# Candidate reason populated
# ---------------------------------------------------------------------------

class TestCandidateReason:
    def test_unknown_class_reason(self):
        d = _call(rule_class="unknown")
        assert "unknown" in d.candidate_reason

    def test_low_confidence_reason_contains_value(self):
        d = _call(rule_class="finance", rule_confidence=40, reason_code="path_rule_finance")
        assert "40" in d.candidate_reason

    def test_below_threshold_reason_contains_class(self):
        d = _call(rule_class="hr", rule_confidence=70, reason_code="path_rule_hr")
        assert "hr" in d.candidate_reason
