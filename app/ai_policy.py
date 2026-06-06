"""AI call policy â€“ decides when AI Foundry should be called.

Conservative policy (default):
  Only call AI when rules produce uncertain results (unknown or low confidence).
  Saves tokens by letting rules handle everything they can classify reliably.

No Azure, no I/O â€“ pure logic; fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Config

# ---------------------------------------------------------------------------
# Classes where rule confidence is sufficient â€“ AI adds no value
# ---------------------------------------------------------------------------
# key = class_label, value = minimum rule confidence that blocks AI
_RULE_SUFFICIENT: dict[str, int] = {
    "br":        90,
    "dsgvo":     85,
    "hr":        80,
    "finance":   80,
    "contract":  75,
    "technical": 70,   # structural/config files â€“ content analysis doesn't help
}

# Extensions for which content-based analysis is meaningless in v0
_BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".dll", ".bin", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".svg",
    ".iso", ".img",
})


@dataclass
class PolicyDecision:
    should_call: bool
    skip_reason: str = ""          # human-readable reason (populated when should_call=False)
    is_ai_candidate: bool = False  # True even when AI is skipped (e.g. budget exhausted)
    candidate_reason: str = ""     # why this blob is a candidate


def should_call_ai(
    rule_class: str,
    rule_confidence: int,
    reason_code: str,
    extension: str,
    config: "Config",
    ai_calls_used: int,
    mode: str,
    dry_run: bool,
) -> PolicyDecision:
    """Evaluate whether AI should be called for a blob.

    Returns a PolicyDecision with should_call=True only when:
      - AI is enabled and provider is set
      - Mode is classify (dry_run allowed: tags controlled by worker)
      - Rule result is uncertain (unknown or confidence below threshold)
      - Budget has not been exhausted
      - Extension is not blocked
    """
    # Determine candidate status first (independent of budget/flags)
    candidate, cand_reason = _is_ai_candidate(
        rule_class, rule_confidence, reason_code, extension
    )

    # Hard gates that prevent AI calls entirely
    if not config.enable_ai:
        return PolicyDecision(False, "ai_disabled",
                              is_ai_candidate=candidate, candidate_reason=cand_reason)
    if config.ai_provider == "none":
        return PolicyDecision(False, "ai_provider_none",
                              is_ai_candidate=candidate, candidate_reason=cand_reason)
    if mode != "classify":
        return PolicyDecision(False, "wrong_mode",
                              is_ai_candidate=candidate, candidate_reason=cand_reason)
    # Not a candidate â†’ no AI
    if not candidate:
        return PolicyDecision(False, f"rule_sufficient:{rule_class}:{rule_confidence}",
                              is_ai_candidate=False)

    # Budget check (after candidate check so ai_candidates counter is accurate)
    if ai_calls_used >= config.ai_max_calls_per_run:
        return PolicyDecision(False, "budget_exhausted",
                              is_ai_candidate=True, candidate_reason=cand_reason)

    # Extension blocked
    if extension.lower() in _BLOCKED_EXTENSIONS:
        return PolicyDecision(False, f"blocked_extension:{extension}",
                              is_ai_candidate=True, candidate_reason=cand_reason)

    return PolicyDecision(True, "", is_ai_candidate=True, candidate_reason=cand_reason)


def _is_ai_candidate(
    rule_class: str,
    rule_confidence: int,
    reason_code: str,
    extension: str,
) -> tuple[bool, str]:
    """Return (is_candidate, reason_string) without budget or flag checks."""
    if rule_class == "unknown" or reason_code == "no_rule_match":
        return True, "class_unknown"
    if rule_confidence < 60:
        return True, f"low_confidence:{rule_confidence}"
    min_conf = _RULE_SUFFICIENT.get(rule_class, -1)
    if min_conf < 0 or rule_confidence < min_conf:
        return True, f"below_class_threshold:{rule_class}:{rule_confidence}"
    return False, ""
