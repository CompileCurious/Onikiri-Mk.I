"""
Onikiri Mk.I — mitmproxy addon for HTTP(S) rule engine.

Load via: mitmproxy --scripts /path/to/proxy_addon.py
Rules path is read from ONIKIRI_RULES_PATH environment variable.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

_RULES_PATH = os.environ.get("ONIKIRI_RULES_PATH", "/data/engagements/mitm-rules.json")


def _load_rules() -> List[Dict[str, Any]]:
    try:
        data = json.loads(Path(_RULES_PATH).read_text())
        active = [r for r in data.get("rules", []) if r.get("enabled", True)]
        return sorted(active, key=lambda r: r.get("priority", 0))
    except (OSError, json.JSONDecodeError):
        return []


def _match_value(cond: Dict[str, Any], subject: str) -> bool:
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


class OnikiriAddon:
    def __init__(self) -> None:
        self.rules: List[Dict[str, Any]] = _load_rules()

    # ------------------------------------------------------------------
    # Request-phase rules (url, domain, request headers)
    # ------------------------------------------------------------------

    def request(self, flow: Any) -> None:  # type: ignore[override]
        from mitmproxy import http as mhttp  # noqa: PLC0415

        for rule in self.rules:
            cond = rule.get("condition", {})
            ctype = cond.get("type", "")

            if ctype == "url":
                subject = flow.request.pretty_url
            elif ctype == "domain":
                subject = flow.request.host
            elif ctype == "header":
                name = cond.get("header_name", "").lower()
                subject = flow.request.headers.get(name, "")
            else:
                continue  # response-phase condition

            if not _match_value(cond, subject):
                continue

            act = rule.get("action", {})
            atype = act.get("type", "")

            if atype == "rewrite_url":
                flow.request.url = act.get("value", flow.request.pretty_url)
            elif atype == "redirect":
                flow.response = mhttp.Response.make(
                    302, b"", {"Location": act.get("value", "/")}
                )
                return
            elif atype == "modify_header":
                hname = act.get("header_name", "")
                if hname:
                    flow.request.headers[hname] = act.get("value", "")
            elif atype == "strip_header":
                hname = act.get("header_name", "")
                if hname and hname in flow.request.headers:
                    del flow.request.headers[hname]
            elif atype == "block":
                flow.response = mhttp.Response.make(
                    403, b"Blocked by Onikiri.", {"Content-Type": "text/plain"}
                )
                return

    # ------------------------------------------------------------------
    # Response-phase rules (mime, html body, response headers)
    # ------------------------------------------------------------------

    def response(self, flow: Any) -> None:  # type: ignore[override]
        if flow.response is None:
            return

        for rule in self.rules:
            cond = rule.get("condition", {})
            ctype = cond.get("type", "")

            if ctype == "mime":
                subject = flow.response.headers.get("content-type", "")
            elif ctype == "html":
                try:
                    subject = flow.response.get_text(strict=False)
                except Exception:
                    subject = ""
            elif ctype == "header":
                name = cond.get("header_name", "").lower()
                subject = flow.response.headers.get(name, "")
            else:
                continue  # request-phase condition

            if not _match_value(cond, subject):
                continue

            act = rule.get("action", {})
            atype = act.get("type", "")

            if atype == "replace_body":
                flow.response.content = act.get("value", "").encode("utf-8")

            elif atype == "substitute":
                try:
                    body = flow.response.get_text(strict=False)
                    find = act.get("find", "")
                    replace = act.get("replace", "")
                    if find:
                        flow.response.text = body.replace(find, replace)
                except Exception:
                    pass

            elif atype == "inject_html":
                try:
                    body = flow.response.get_text(strict=False)
                    snippet = act.get("value", "")
                    if snippet:
                        lower_body = body.lower()
                        idx = lower_body.rfind("</body>")
                        if idx >= 0:
                            flow.response.text = body[:idx] + snippet + body[idx:]
                        else:
                            flow.response.text = body + snippet
                except Exception:
                    pass

            elif atype == "modify_header":
                hname = act.get("header_name", "")
                if hname:
                    flow.response.headers[hname] = act.get("value", "")

            elif atype == "strip_header":
                hname = act.get("header_name", "")
                if hname and hname in flow.response.headers:
                    del flow.response.headers[hname]

    # ------------------------------------------------------------------
    # TLS-stripping: downgrade HTTPS redirects to HTTP
    # ------------------------------------------------------------------

    def responseheaders(self, flow: Any) -> None:  # type: ignore[override]
        if flow.response is None:
            return
        loc = flow.response.headers.get("location", "")
        if loc.startswith("https://"):
            flow.response.headers["location"] = "http://" + loc[len("https://"):]
        # Strip HSTS to prevent browser enforcement
        flow.response.headers.pop("strict-transport-security", None)


addons = [OnikiriAddon()]
