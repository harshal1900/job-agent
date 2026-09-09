"""ngrok tunnel management — exposes the local FastAPI server's /respond
(approve/reject) endpoints during an approval window.

Gated behind settings.ENABLE_NGROK_TUNNEL (default False, see
config/settings.py) per PRD risk #2: a public tunnel should only be up
while actually waiting on an approval, not left running by default every
time the server starts.

Uses whatever real `ngrok` binary is already installed system-wide — i.e.
the one you already ran `ngrok config add-authtoken` against — rather than
letting pyngrok download and manage a separate copy, so it picks up your
existing auth without any extra config here. NGROK_AUTHTOKEN in .env is
only needed as a fallback if no local ngrok install is already
authenticated.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys

from pyngrok import conf, ngrok
from pyngrok.ngrok import NgrokTunnel

from config.settings import get_settings

logger = logging.getLogger(__name__)

_active_tunnel: NgrokTunnel | None = None


def _find_system_ngrok() -> str | None:
    """shutil.which("ngrok") is unreliable once pyngrok is pip-installed in
    the active venv: pyngrok ships a console-script shim also named `ngrok`
    (a Python wrapper, not the real binary) in venv/bin, which sits ahead of
    the real system install on PATH. Search PATH directly, skipping any
    entry inside the current venv, so this always resolves to the actual
    ngrok binary the user authenticated via `ngrok config add-authtoken`.
    """
    venv_bin = os.path.join(sys.prefix, "bin")
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.abspath(directory) == os.path.abspath(venv_bin):
            continue
        candidate = shutil.which("ngrok", path=directory)
        if candidate:
            return candidate
    return None


def start_tunnel(port: int) -> str:
    """Open an ngrok tunnel to `port` and update settings.PUBLIC_BASE_URL
    in place so every URL built after this call (approval links, etc.) uses
    the live public URL. Returns the public HTTPS URL.
    """
    global _active_tunnel
    settings = get_settings()

    system_ngrok = _find_system_ngrok()
    if system_ngrok:
        conf.set_default(conf.PyngrokConfig(ngrok_path=system_ngrok))
    else:
        logger.warning(
            "No system ngrok binary found outside the venv — pyngrok will "
            "download and manage its own copy instead."
        )
    if settings.NGROK_AUTHTOKEN:
        ngrok.set_auth_token(settings.NGROK_AUTHTOKEN)

    _active_tunnel = ngrok.connect(port, "http")
    public_url = _active_tunnel.public_url
    if public_url.startswith("http://"):
        public_url = "https://" + public_url[len("http://") :]

    settings.PUBLIC_BASE_URL = public_url
    logger.info("ngrok tunnel open: %s -> localhost:%d", public_url, port)
    return public_url


def stop_tunnel() -> None:
    global _active_tunnel
    if _active_tunnel is not None:
        ngrok.disconnect(_active_tunnel.public_url)
        _active_tunnel = None
    ngrok.kill()
    logger.info("ngrok tunnel closed")
