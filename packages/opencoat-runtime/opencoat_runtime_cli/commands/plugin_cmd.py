"""``opencoat plugin`` — host plugin scaffolding (post-M5 DX sprint).

``plugin install <host>`` copies a small, lint-clean starter set of
files into ``--out`` (default ``./opencoat_plugin``) so a user can wire a
new host adapter in under a minute.

The starter files live under :mod:`opencoat_runtime_cli.plugin_templates`
and are real, importable Python modules — they pass ``ruff check`` /
``ruff format --check`` as a side effect of the workspace lint, which
keeps the scaffold from drifting away from the live SDK.

``list`` enumerates the available host templates; ``disable`` is
reserved for the runtime-side plugin registry (post-M6).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Mapping
from importlib.resources import as_file, files
from pathlib import Path

# Available host names → (one-line description, template subpackage).
_AVAILABLE_HOSTS: Mapping[str, tuple[str, str]] = {
    "openclaw": (
        "OpenClaw event-bus host (uses install_hooks + OpenClawAdapter).",
        "opencoat_runtime_cli.plugin_templates.openclaw",
    ),
    "custom": (
        "Skeleton HostAdapter for a bespoke framework — fill in 3 methods.",
        "opencoat_runtime_cli.plugin_templates.custom",
    ),
}

_TEMPLATE_FILES: tuple[str, ...] = (
    "bootstrap_opencoat.py",
    "host_adapter.py",
    "concerns.py",
)
_PACKAGE_INIT = "__init__.py"
_DEFAULT_OUT_DIR = Path("opencoat_plugin")


def _write_package_init(dst: Path, host: str) -> None:
    dst.write_text(
        f'"""OpenCOAT host plugin scaffold — generated for {host!r}."""\n',
        encoding="utf-8",
    )


def _copy_templates(host: str, out: Path, *, force: bool) -> int:
    """Copy the four starter files for ``host`` into ``out``.

    Returns the CLI exit code: 0 on success, 1 when a destination file
    already exists and ``force`` is false (validated *before* any write
    so a partial scaffold never lands).
    """
    _, package = _AVAILABLE_HOSTS[host]
    template_pkg = files(package)

    init_dst = out / _PACKAGE_INIT
    file_dsts = [out / name for name in _TEMPLATE_FILES]
    for dst in (init_dst, *file_dsts):
        if dst.exists() and not force:
            print(
                f"plugin install: {dst} already exists (use --force to overwrite)",
                file=sys.stderr,
            )
            return 1

    _write_package_init(init_dst, host)
    written: list[Path] = [init_dst]
    for name, dst in zip(_TEMPLATE_FILES, file_dsts, strict=True):
        src = template_pkg / name
        with as_file(src) as src_path:
            shutil.copyfile(src_path, dst)
        written.append(dst)

    print(f"plugin install: wrote {len(written)} files into {out.resolve()}")
    for path in written:
        print(f"  • {path}")
    print()
    print("Next:")
    if host == "openclaw":
        print("  1. Start a daemon:           opencoat runtime up")
        print("  2. Seed some concerns:        opencoat concern import --demo")
        print("  3. Call from your app:        bootstrap_opencoat.install(your_openclaw_host)")
        print("     (uses HTTP to the daemon; for an embedded runtime instead see")
        print("      install_in_process()).")
    else:
        print("  1. Start a daemon:           opencoat runtime up")
        print("  2. Seed some concerns:        opencoat concern import --demo")
        print("  3. Fill in map_host_event / apply_injection in host_adapter.py.")
        print("  4. Drive the adapter from your agent loop, using:")
        print("       client = bootstrap_opencoat.daemon_client()")
        print("       client.emit(jp)   # forwards over HTTP to the daemon")
    return 0


def _install(args: argparse.Namespace) -> int:
    host = args.host
    out = Path(args.out) if args.out else _DEFAULT_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    return _copy_templates(host, out, force=bool(args.force))


def _list(_args: argparse.Namespace) -> int:
    width = max(len(name) for name in _AVAILABLE_HOSTS)
    for name, (desc, _pkg) in _AVAILABLE_HOSTS.items():
        print(f"{name:<{width}}  {desc}")
    return 0


def _disable(args: argparse.Namespace) -> int:
    print(
        f"plugin disable: runtime-side plugin registry lands post-M6 (asked for {args.name!r}).",
        file=sys.stderr,
    )
    return 2


def register(sub: argparse._SubParsersAction) -> None:
    plugin = sub.add_parser(
        "plugin",
        help="manage host / matcher / advisor plugins",
        description="Scaffold and manage OpenCOAT host plugins.",
    )
    actions = plugin.add_subparsers(dest="action", required=True)

    install = actions.add_parser(
        "install",
        help="scaffold starter files for a host plugin",
        description=(
            "Copy a lint-clean starter set "
            "(__init__.py + bootstrap_opencoat.py + host_adapter.py + concerns.py) "
            "into the target directory."
        ),
    )
    install.add_argument("host", choices=sorted(_AVAILABLE_HOSTS))
    install.add_argument(
        "--out",
        default=None,
        help=f"target directory (default: ./{_DEFAULT_OUT_DIR})",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing files in the target directory",
    )
    install.set_defaults(func=_install)

    lst = actions.add_parser("list", help="list available host plugin templates")
    lst.set_defaults(func=_list)

    disable = actions.add_parser("disable", help="disable a loaded plugin (post-M6)")
    disable.add_argument("name")
    disable.set_defaults(func=_disable)


__all__ = ["register"]
