"""``opencoat service`` — OS-level autostart for the OpenCOAT runtime daemon.

* **macOS**: a user LaunchAgent under ``~/Library/LaunchAgents/``.
* **Linux**: a systemd user unit under ``<home>/.config/systemd/user/``.

The daemon is started by the session manager at login (and at boot when
`user lingering <https://www.freedesktop.org/software/systemd/man/loginctl.html>`_
is enabled on Linux). It is **not** tied to Cursor, OpenClaw, or any host
agent process.

API keys are not embedded in the generated files. Use ``opencoat configure
llm`` (inline secrets or ``~/.opencoat/opencoat.env``) and extend the unit
with ``EnvironmentFile`` / ``Environment`` when needed.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_LAUNCHD_LABEL = "io.opencoat.runtime-daemon"
_SYSTEMD_UNIT = "opencoat-runtime.service"


def _pid_at_home(home: Path) -> Path:
    """PID file path under ``home`` (matches ``runtime`` CLI default layout)."""
    return home / ".opencoat" / "opencoat.pid"


def _systemd_user_dir(home: Path) -> Path:
    """Where systemd --user looks for units for this logical home."""
    if home.resolve() == Path.home().resolve():
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg).expanduser() / "systemd" / "user"
    return home / ".config" / "systemd" / "user"


def _launchd_plist_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / f"{_LAUNCHD_LABEL}.plist"


def _systemd_unit_path(home: Path) -> Path:
    return _systemd_user_dir(home) / _SYSTEMD_UNIT


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=True,
    )


def _plist_payload(*, home: Path, python_exe: str, config: Path | None) -> dict[str, Any]:
    opencoat_dir = home / ".opencoat"
    log_path = opencoat_dir / "daemon-launchd.log"
    pid_path = _pid_at_home(home)
    args: list[str] = [python_exe, "-m", "opencoat_runtime_daemon"]
    if config is not None:
        args += ["--config", str(config.resolve())]
    args += ["--pid-file", str(pid_path.resolve())]
    return {
        "Label": _LAUNCHD_LABEL,
        "ProgramArguments": args,
        "EnvironmentVariables": {
            "OPENCOAT_PID_FILE": str(pid_path.resolve()),
        },
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(log_path.resolve()),
        "StandardErrorPath": str(log_path.resolve()),
        "WorkingDirectory": str(home.resolve()),
    }


def _plist_bytes(payload: dict[str, Any]) -> bytes:
    fmt = getattr(plistlib, "FMT_XML", plistlib.FMT_BINARY)
    return plistlib.dumps(payload, fmt=fmt)


def _systemd_unit_text(*, home: Path, python_exe: str, config: Path | None) -> str:
    cfg = ""
    if config is not None:
        cfg = f" --config {config.resolve()}"
    pid = _pid_at_home(home).resolve()
    lines = [
        "[Unit]",
        "Description=OpenCOAT runtime daemon (HTTP JSON-RPC)",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        f"Environment=OPENCOAT_PID_FILE={pid}",
        "# Optional: uncomment after `opencoat configure llm` created the file",
        "# EnvironmentFile=-%h/.opencoat/opencoat.env",
        f"ExecStart={python_exe} -m opencoat_runtime_daemon{cfg} --pid-file {pid}",
        "Restart=no",
        f"WorkingDirectory={home.resolve()}",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ]
    return "\n".join(lines)


def _install_launchd(home: Path, *, config: Path | None, python_exe: str) -> int:
    plist_path = _launchd_plist_path(home)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _plist_payload(home=home, python_exe=python_exe, config=config)
    plist_path.write_bytes(_plist_bytes(payload))
    domain = _launchd_domain()
    resolved = str(plist_path.resolve())
    _run(["launchctl", "bootout", domain, resolved])
    br = _run(["launchctl", "bootstrap", domain, resolved])
    if br.returncode != 0:
        print(f"service install: launchctl bootstrap failed:\n{br.stderr}", file=sys.stderr)
        return 1
    print(f"service install: wrote {plist_path}", file=sys.stderr)
    print(
        "  Stop: opencoat service stop   Restart: opencoat service restart\n"
        "  (or `launchctl bootout gui/$UID …` / `launchctl bootstrap …`)",
        file=sys.stderr,
    )
    return 0


def _install_systemd(home: Path, *, config: Path | None, python_exe: str) -> int:
    unit_path = _systemd_unit_path(home)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        _systemd_unit_text(home=home, python_exe=python_exe, config=config), encoding="utf-8"
    )
    dr = _run(["systemctl", "--user", "daemon-reload"])
    if dr.returncode != 0:
        print(f"service install: systemctl daemon-reload failed:\n{dr.stderr}", file=sys.stderr)
        return 1
    en = _run(["systemctl", "--user", "enable", _SYSTEMD_UNIT])
    if en.returncode != 0:
        print(f"service install: systemctl enable failed:\n{en.stderr}", file=sys.stderr)
        return 1
    st = _run(["systemctl", "--user", "restart", _SYSTEMD_UNIT])
    if st.returncode != 0:
        st = _run(["systemctl", "--user", "start", _SYSTEMD_UNIT])
    if st.returncode != 0:
        print(
            "service install: unit written but start failed — "
            "try `systemctl --user start opencoat-runtime.service` manually:\n"
            f"{st.stderr}",
            file=sys.stderr,
        )
        return 1
    print(f"service install: wrote {unit_path}", file=sys.stderr)
    print(
        "  For boot-without-login: loginctl enable-linger $USER\n"
        "  Status: systemctl --user status opencoat-runtime.service",
        file=sys.stderr,
    )
    return 0


def _uninstall_launchd(home: Path) -> int:
    plist_path = _launchd_plist_path(home)
    if not plist_path.is_file():
        print(f"service uninstall: not installed ({plist_path} missing)", file=sys.stderr)
        return 0
    domain = _launchd_domain()
    _run(["launchctl", "bootout", domain, str(plist_path.resolve())])
    plist_path.unlink(missing_ok=True)
    print(f"service uninstall: removed {plist_path}", file=sys.stderr)
    return 0


def _uninstall_systemd(home: Path) -> int:
    unit_path = _systemd_unit_path(home)
    if not unit_path.is_file():
        print(f"service uninstall: not installed ({unit_path} missing)", file=sys.stderr)
        return 0
    _run(["systemctl", "--user", "disable", "--now", _SYSTEMD_UNIT])
    unit_path.unlink(missing_ok=True)
    _run(["systemctl", "--user", "daemon-reload"])
    print(f"service uninstall: removed {unit_path}", file=sys.stderr)
    return 0


def _status_launchd() -> int:
    pr = _run(["launchctl", "print", f"{_launchd_domain()}/{_LAUNCHD_LABEL}"])
    sys.stdout.write(pr.stdout or pr.stderr or "")
    return 0 if pr.returncode == 0 else 3


def _status_systemd() -> int:
    pr = _run(["systemctl", "--user", "--no-pager", "status", _SYSTEMD_UNIT])
    sys.stdout.write(pr.stdout or pr.stderr or "")
    return 0 if pr.returncode == 0 else pr.returncode


def _launchd_plist_resolved(home: Path) -> str:
    return str(_launchd_plist_path(home).resolve())


def _restart_launchd(home: Path) -> int:
    domain = _launchd_domain()
    plist = _launchd_plist_resolved(home)
    _run(["launchctl", "bootout", domain, plist])
    br = _run(["launchctl", "bootstrap", domain, plist])
    if br.returncode != 0:
        print(f"service restart: {br.stderr}", file=sys.stderr)
        return 1
    return 0


def _restart_systemd() -> int:
    pr = _run(["systemctl", "--user", "restart", _SYSTEMD_UNIT])
    if pr.returncode != 0:
        print(f"service restart: {pr.stderr}", file=sys.stderr)
        return 1
    return 0


def _handle_install(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    python_exe = str(Path(args.python).expanduser()) if args.python else sys.executable
    config = Path(args.config).expanduser() if args.config else None
    if config is not None and not config.is_file():
        print(f"service install: config file not found: {config}", file=sys.stderr)
        return 2
    (home / ".opencoat").mkdir(parents=True, exist_ok=True)
    system = sys.platform
    if system == "darwin":
        return _install_launchd(home, config=config, python_exe=python_exe)
    if system.startswith("linux"):
        if shutil.which("systemctl") is None:
            print(
                "service install: systemctl not found — install systemd user session",
                file=sys.stderr,
            )
            return 2
        return _install_systemd(home, config=config, python_exe=python_exe)
    print(f"service install: unsupported platform {system!r}", file=sys.stderr)
    return 2


def _handle_uninstall(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    if sys.platform == "darwin":
        return _uninstall_launchd(home)
    if sys.platform.startswith("linux"):
        return _uninstall_systemd(home)
    print(f"service uninstall: unsupported platform {sys.platform!r}", file=sys.stderr)
    return 2


def _handle_status(_args: argparse.Namespace) -> int:
    if sys.platform == "darwin":
        return _status_launchd()
    if sys.platform.startswith("linux"):
        return _status_systemd()
    print(f"service status: unsupported platform {sys.platform!r}", file=sys.stderr)
    return 2


def _handle_start(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    if sys.platform == "darwin":
        plist = _launchd_plist_path(home)
        if not plist.is_file():
            print(
                "service start: plist missing — run `opencoat service install` first",
                file=sys.stderr,
            )
            return 2
        domain = _launchd_domain()
        resolved = str(plist.resolve())
        pr = _run(["launchctl", "bootstrap", domain, resolved])
        if pr.returncode != 0:
            pr = _run(["launchctl", "kickstart", f"{domain}/{_LAUNCHD_LABEL}"])
        if pr.returncode != 0:
            print(pr.stderr, file=sys.stderr)
            return 1
        return 0
    if sys.platform.startswith("linux"):
        pr = _run(["systemctl", "--user", "start", _SYSTEMD_UNIT])
        if pr.returncode != 0:
            print(pr.stderr, file=sys.stderr)
            return 1
        return 0
    print(f"service start: unsupported platform {sys.platform!r}", file=sys.stderr)
    return 2


def _handle_stop(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    if sys.platform == "darwin":
        plist = _launchd_plist_path(home)
        if not plist.is_file():
            print("service stop: plist missing — nothing to boot out", file=sys.stderr)
            return 0
        pr = _run(["launchctl", "bootout", _launchd_domain(), str(plist.resolve())])
        if pr.returncode != 0 and "No such process" not in (pr.stderr or ""):
            print(pr.stderr, file=sys.stderr)
            return 1
        return 0
    if sys.platform.startswith("linux"):
        pr = _run(["systemctl", "--user", "stop", _SYSTEMD_UNIT])
        if pr.returncode != 0:
            print(pr.stderr, file=sys.stderr)
            return 1
        return 0
    print(f"service stop: unsupported platform {sys.platform!r}", file=sys.stderr)
    return 2


def _handle_restart(args: argparse.Namespace) -> int:
    home = Path(args.home).expanduser()
    if sys.platform == "darwin":
        plist = _launchd_plist_path(home)
        if not plist.is_file():
            print(
                "service restart: plist missing — run `opencoat service install` first",
                file=sys.stderr,
            )
            return 2
        return _restart_launchd(home)
    if sys.platform.startswith("linux"):
        return _restart_systemd()
    print(f"service restart: unsupported platform {sys.platform!r}", file=sys.stderr)
    return 2


_ACTIONS: dict[str, Any] = {
    "install": _handle_install,
    "uninstall": _handle_uninstall,
    "status": _handle_status,
    "start": _handle_start,
    "stop": _handle_stop,
    "restart": _handle_restart,
}


def _handle(args: argparse.Namespace) -> int:
    fn = _ACTIONS.get(args.action)
    if fn is None:
        return 2
    return int(fn(args) or 0)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "service",
        help="install / manage OS autostart for the OpenCOAT runtime daemon",
    )
    p.add_argument(
        "action",
        choices=sorted(_ACTIONS.keys()),
        help="install | uninstall | status | start | stop | restart",
    )
    p.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="home directory for plist/unit layout (default: real ~)",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional daemon YAML passed as --config (default: bundled default.yaml only)",
    )
    p.add_argument(
        "--python",
        type=Path,
        default=None,
        help=f"python executable for ExecStart (default: {sys.executable})",
    )
    p.set_defaults(func=_handle)


__all__ = ["register"]
