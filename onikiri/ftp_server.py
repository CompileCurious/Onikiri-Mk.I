from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

_LOG = logging.getLogger(__name__)


def start_ftp_server(config: Dict[str, Any]) -> Optional[threading.Thread]:
    """Start a pyftpdlib FTP server as a daemon thread.

    The FTP root is /userdata/ (configurable via config["ftp"]["root"]).
    Toishi navigates to:
      /captures/engagements/  — packed engagement archives (.tar.gz)
      /payload.img            — USB mass storage payload image

    Returns the thread on success, or None if pyftpdlib is unavailable.
    """
    try:
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.servers import FTPServer
    except ImportError:
        _LOG.warning("pyftpdlib not installed; FTP server disabled")
        return None

    ftp_cfg = config.get("ftp", {})
    host = ftp_cfg.get("listen", "0.0.0.0")
    port = int(ftp_cfg.get("port", 2121))
    user = ftp_cfg.get("user", "onikiri")
    passwd = ftp_cfg.get("password", "onikiri")
    root = Path(ftp_cfg.get("root", "/userdata"))
    root.mkdir(parents=True, exist_ok=True)

    authorizer = DummyAuthorizer()
    # perm string: e=CWD l=LIST r=RETR a=APPE d=DELETE f=RENAME m=MKDIR w=STOR M=chmod T=mtime
    authorizer.add_user(user, passwd, str(root), perm="elradfmwMT")

    class OnikiriFTPHandler(FTPHandler):
        banner = "ONIKIRI MK.I — TOISHI COMPANION FTP"
        passive_ports = range(60000, 60100)

    OnikiriFTPHandler.authorizer = authorizer

    server = FTPServer((host, port), OnikiriFTPHandler)

    def _serve() -> None:
        _LOG.info("FTP server listening on %s:%d (root: %s)", host, port, root)
        try:
            server.serve_forever()
        except Exception as exc:
            _LOG.error("FTP server error: %s", exc)

    thread = threading.Thread(target=_serve, daemon=True, name="onikiri-ftp")
    thread.start()
    return thread
