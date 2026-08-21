"""Rule-based eligibility engine.

Deterministic, explainable scoring. Runs fully offline (no LLM required) and
produces reasons, unmet criteria and a confidence score for each opportunity.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EligibilityResult:
    eligible: bool
    score: float  # 0..1 fraction of criteria satisfied
    confidence: float  # 0..1 how sure we are (based on data completeness)
    reasons: list[str] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)


def _norm(value) -> str:
    return str(value).strip().lower() if value is not None else ""


def evaluate(profile: dict, opportunity: dict) -> EligibilityResult:
    criteria = opportunity.get("criteria", {})
    reasons: list[str] = []
    unmet: list[str] = []

    checks_total = 0
    checks_passed = 0
    known_fields = 0  # how many profile fields were actually available for checks

    def record(passed: bool, ok_msg: str, fail_msg: str, had_data: bool = True) -> None:
        nonlocal checks_total, checks_passed, known_fields
        checks_total += 1
        if had_data:
            known_fields += 1
        if passed:
            checks_passed += 1
            reasons.append(ok_msg)
        else:
            unmet.append(fail_msg)

    # Category
    if "category" in criteria:
        allowed = [c.lower() for c in criteria["category"]]
        val = _norm(profile.get("category"))
        record(bool(val) and val in allowed,
               f"Category '{profile.get('category')}' is eligible",
               f"Requires category: {', '.join(criteria['category'])}",
               had_data=bool(val))

    # State / domicile
    if "state" in criteria:
        allowed = [s.lower() for s in criteria["state"]]
        val = _norm(profile.get("state"))
        record(bool(val) and val in allowed,
               f"State '{profile.get('state')}' matches",
               f"Requires domicile in: {', '.join(criteria['state'])}",
               had_data=bool(val))

    # Education level
    if "education_level" in criteria:
        allowed = [e.lower() for e in criteria["education_level"]]
        val = _norm(profile.get("education_level"))
        record(bool(val) and val in allowed,
               f"Education level '{profile.get('education_level')}' qualifies",
               f"Requires education level: {', '.join(criteria['education_level'])}",
               had_data=bool(val))

    # Field of study (partial keyword match)
    if "field_of_study" in criteria:
        allowed = [f.lower() for f in criteria["field_of_study"]]
        val = _norm(profile.get("field_of_study"))
        passed = bool(val) and any(a in val or val in a for a in allowed)
        record(passed,
               f"Field of study '{profile.get('field_of_study')}' is relevant",
               f"Intended for fields: {', '.join(criteria['field_of_study'])}",
               had_data=bool(val))

    # Gender
    if "gender" in criteria:
        allowed = [g.lower() for g in criteria["gender"]]
        val = _norm(profile.get("gender"))
        record(bool(val) and val in allowed,
               f"Open to {', '.join(criteria['gender'])} applicants",
               f"Restricted to: {', '.join(criteria['gender'])}",
               had_data=bool(val))

    # Income ceiling
    if "max_income" in criteria:
        income = profile.get("annual_income")
        has = income is not None
        passed = has and income <= criteria["max_income"]
        record(passed,
               f"Income \u20b9{income:,} is within the \u20b9{criteria['max_income']:,} limit" if has else "",
               f"Family income must be \u2264 \u20b9{criteria['max_income']:,}",
               had_data=has)

    # Age ceiling
    if "max_age" in criteria:
        age = profile.get("age")
        has = age is not None
        passed = has and age <= criteria["max_age"]
        record(passed,
               f"Age {age} is within the limit of {criteria['max_age']}" if has else "",
               f"Age must be \u2264 {criteria['max_age']}",
               had_data=has)

    # Disability requirement
    if criteria.get("disability") is True:
        val = bool(profile.get("disability"))
        record(val,
               "Meets disability eligibility",
               "Requires a disability certificate (40%+)",
               had_data=True)

    # Goal keywords (for grants/entrepreneurship schemes)
    if "goals_keywords" in criteria:
        goals = _norm(profile.get("goals"))
        keys = [k.lower() for k in criteria["goals_keywords"]]
        passed = bool(goals) and any(k in goals for k in keys)
        record(passed,
               "Your stated goals align with this scheme",
               f"Best suited if your goal relates to: {', '.join(criteria['goals_keywords'])}",
               had_data=bool(goals))

    if checks_total == 0:
        # No criteria to check -> open to all
        return EligibilityResult(True, 1.0, 0.6, ["Open to all eligible citizens"], [])

    score = checks_passed / checks_total
    # Confidence reflects how much profile data we actually had to judge with.
    data_completeness = known_fields / checks_total
    confidence = round(0.5 + 0.5 * data_completeness, 2)
    eligible = len(unmet) == 0

    # Remove any empty reason strings produced when data was missing
    reasons = [r for r in reasons if r]

    return EligibilityResult(eligible, round(score, 2), confidence, reasons, unmet)
