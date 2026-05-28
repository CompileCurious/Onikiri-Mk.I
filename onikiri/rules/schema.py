from __future__ import annotations

from typing import Any, Dict, List

CONDITION_TYPES: tuple[str, ...] = (
    "url",
    "domain",
    "mime",
    "html",
    "header",
)

OPERATORS: tuple[str, ...] = (
    "contains",
    "equals",
    "starts_with",
    "ends_with",
    "matches",
)

ACTION_TYPES: tuple[str, ...] = (
    "rewrite_url",
    "redirect",
    "replace_body",
    "substitute",
    "modify_header",
    "inject_html",
    "strip_header",
    "block",
)

# Human-readable labels used by the HMI
CONDITION_LABELS: Dict[str, str] = {
    "url": "URL",
    "domain": "DOMAIN",
    "mime": "MIME TYPE",
    "html": "HTML CONTENT",
    "header": "HEADER",
}

OPERATOR_LABELS: Dict[str, str] = {
    "contains": "CONTAINS",
    "equals": "EQUALS",
    "starts_with": "STARTS WITH",
    "ends_with": "ENDS WITH",
    "matches": "MATCHES (REGEX)",
}

ACTION_LABELS: Dict[str, str] = {
    "rewrite_url": "REWRITE URL TO",
    "redirect": "REDIRECT TO",
    "replace_body": "REPLACE BODY WITH",
    "substitute": "SUBSTITUTE TEXT",
    "modify_header": "SET HEADER",
    "inject_html": "INJECT HTML",
    "strip_header": "STRIP HEADER",
    "block": "BLOCK REQUEST",
}

# Which action types require a secondary value field (find/replace or header name)
DUAL_VALUE_ACTIONS = ("substitute", "modify_header", "strip_header")


def validate_rule(rule: Dict[str, Any]) -> List[str]:
    """Return a list of validation errors. Empty list means the rule is valid."""
    errors: List[str] = []

    if not rule.get("id"):
        errors.append("rule missing 'id'")
    if not isinstance(rule.get("name"), str) or not str(rule.get("name", "")).strip():
        errors.append("rule missing 'name'")
    if not isinstance(rule.get("priority"), int):
        errors.append("rule 'priority' must be an integer")
    if not isinstance(rule.get("enabled"), bool):
        errors.append("rule 'enabled' must be a boolean")

    cond = rule.get("condition")
    if not isinstance(cond, dict):
        errors.append("rule missing 'condition' object")
    else:
        if cond.get("type") not in CONDITION_TYPES:
            errors.append(
                f"condition 'type' must be one of {CONDITION_TYPES}, got {cond.get('type')!r}"
            )
        if cond.get("operator") not in OPERATORS:
            errors.append(
                f"condition 'operator' must be one of {OPERATORS}, got {cond.get('operator')!r}"
            )
        if "value" not in cond:
            errors.append("condition missing 'value'")

    act = rule.get("action")
    if not isinstance(act, dict):
        errors.append("rule missing 'action' object")
    else:
        if act.get("type") not in ACTION_TYPES:
            errors.append(
                f"action 'type' must be one of {ACTION_TYPES}, got {act.get('type')!r}"
            )

    return errors
