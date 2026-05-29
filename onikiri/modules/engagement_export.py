from __future__ import annotations

import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from onikiri.module_base import BaseModule, SupervisorContext


class EngagementExportModule(BaseModule):
    name = "engagement_export"
    label = "ENGAGEMENT EXPORT"
    default_action = "list"

    def actions(self) -> tuple[str, ...]:
        return ("list", "pack", "delete")

    def _base(self, context: SupervisorContext) -> Path:
        path = Path(context.config.get("engagement_data_dir", "/userdata/captures/engagements"))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _safe_name(self, name: str) -> str | None:
        """Return name if safe, None if it contains path traversal."""
        if not name or "/" in name or name.startswith("."):
            return None
        return name

    def action_list(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        base = self._base(context)
        sessions = []
        for item in sorted(base.iterdir()):
            if item.is_dir():
                size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                sessions.append({
                    "name": item.name,
                    "type": "session",
                    "size_bytes": size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                })
            elif item.name.endswith(".tar.gz"):
                sessions.append({
                    "name": item.name,
                    "type": "archive",
                    "size_bytes": item.stat().st_size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                })
        return {"status": "ok", "sessions": sessions}

    def action_pack(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        session = self._safe_name(params.get("session", ""))
        if not session:
            return {"status": "error", "error": "invalid session name"}
        base = self._base(context)
        src = base / session
        if not src.is_dir():
            return {"status": "error", "error": f"session directory not found: {session}"}
        archive = base / f"{session}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src, arcname=session)
        # FTP path is relative to /userdata/ (FTP root), e.g. /captures/engagements/<name>.tar.gz
        try:
            ftp_path = "/" + str(archive.relative_to("/userdata"))
        except ValueError:
            ftp_path = str(archive)
        return {
            "status": "ok",
            "session": session,
            "archive": str(archive),
            "ftp_path": ftp_path,
            "size_bytes": archive.stat().st_size,
        }

    def action_delete(self, params: Dict[str, Any], context: SupervisorContext) -> Dict[str, Any]:
        session = self._safe_name(params.get("session", ""))
        if not session:
            return {"status": "error", "error": "invalid session name"}
        base = self._base(context)
        removed = []
        src = base / session
        if src.is_dir():
            shutil.rmtree(src)
            removed.append(str(src))
        # Strip .tar.gz suffix if the caller passed the archive name directly
        stem = session[: -len(".tar.gz")] if session.endswith(".tar.gz") else session
        archive = base / f"{stem}.tar.gz"
        if archive.is_file():
            archive.unlink()
            removed.append(str(archive))
        if not removed:
            return {"status": "error", "error": "session not found"}
        return {"status": "ok", "removed": removed}
