from __future__ import annotations

import re
from typing import Any, Dict, List


class RuleEngine:
    """Applies an ordered list of enabled MITM rules to a request/response context dict."""

    def __init__(self, rules: List[Dict[str, Any]]) -> None:
        active = [r for r in rules if r.get("enabled", True)]
        self.rules: List[Dict[str, Any]] = sorted(active, key=lambda r: r.get("priority", 0))

    # ------------------------------------------------------------------
    # Subject extraction
    # ------------------------------------------------------------------

    def _subject(self, cond: Dict[str, Any], ctx: Dict[str, Any]) -> str:
        ctype = cond.get("type", "")
        if ctype == "url":
            return ctx.get("url", "")
        if ctype == "domain":
            return ctx.get("domain", "")
        if ctype == "mime":
            return ctx.get("content_type", "")
        if ctype == "html":
            return ctx.get("body", "")
        if ctype == "header":
            name = cond.get("header_name", "").lower()
            return ctx.get("headers", {}).get(name, "")
        return ""

    # ------------------------------------------------------------------
    # Condition matching
    # ------------------------------------------------------------------

    def _match(self, cond: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
        subject = self._subject(cond, ctx)
        value = cond.get("value", "")
        op = cond.get("operator", "contains")
        sl, vl = subject.lower(), value.lower()
        if op == "contains":
            return vl in sl
        if op == "equals":
            return sl == vl
        if op == "starts_with":
            return sl.startswith(vl)
        if op == "ends_with":
            return sl.endswith(vl)
        if op == "matches":
            try:
                return bool(re.search(value, subject, re.IGNORECASE))
            except re.error:
                return False
        return False

    # ------------------------------------------------------------------
    # Action application
    # ------------------------------------------------------------------

    def _apply(self, act: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(ctx)
        result.setdefault("headers", dict(ctx.get("headers", {})))
        atype = act.get("type", "")

        if atype == "rewrite_url":
            result["url"] = act.get("value", ctx.get("url", ""))

        elif atype == "redirect":
            result["redirect_to"] = act.get("value", "")

        elif atype == "replace_body":
            result["body"] = act.get("value", "")

        elif atype == "substitute":
            body = ctx.get("body", "")
            find = act.get("find", "")
            replace = act.get("replace", "")
            result["body"] = body.replace(find, replace) if find else body

        elif atype == "modify_header":
            name = act.get("header_name", "").lower()
            if name:
                result["headers"][name] = act.get("value", "")

        elif atype == "inject_html":
            body = ctx.get("body", "")
            snippet = act.get("value", "")
            if snippet and "</body>" in body.lower():
                idx = body.lower().rfind("</body>")
                result["body"] = body[:idx] + snippet + body[idx:]
            elif snippet:
                result["body"] = body + snippet

        elif atype == "strip_header":
            name = act.get("header_name", "").lower()
            result["headers"].pop(name, None)

        elif atype == "block":
            result["blocked"] = True

        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Run all matching rules against ctx and return the transformed context."""
        result = dict(ctx)
        for rule in self.rules:
            if self._match(rule["condition"], result):
                result = self._apply(rule["action"], result)
                if result.get("blocked"):
                    break
        return result

    def test_rule(self, rule: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single rule against a context. Returns match result and transformed context."""
        matched = self._match(rule["condition"], ctx)
        output = self._apply(rule["action"], ctx) if matched else dict(ctx)
        return {
            "matched": matched,
            "input": ctx,
            "output": output,
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
        }
