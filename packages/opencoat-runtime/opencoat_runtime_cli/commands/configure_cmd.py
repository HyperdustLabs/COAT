"""``opencoat configure llm`` — guided daemon LLM credential setup.

Writes a small ``~/.opencoat/daemon.yaml`` fragment (``llm.*`` only) and,
by default, a ``~/.opencoat/opencoat.env`` file with provider API keys so
``provider: auto`` can resolve without pasting secrets into YAML.

The daemon does **not** auto-load ``opencoat.env`` — the operator must
``source`` it in the same shell before ``opencoat runtime up`` (or export
the vars in their shell profile / systemd unit). The wizard prints the
exact commands at the end.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import stat
import sys
from pathlib import Path
from typing import Any, Literal

import yaml

Mode = Literal["env-file", "inline"]

_DEFAULT_YAML_REL = Path(".opencoat") / "daemon.yaml"
_DEFAULT_ENV_REL = Path(".opencoat") / "opencoat.env"


def _default_yaml_path() -> Path:
    return Path.home() / _DEFAULT_YAML_REL


def _default_env_path() -> Path:
    return Path.home() / _DEFAULT_ENV_REL


def _chmod_secret(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        if key and key not in out:
            out[key] = v.strip().strip('"').strip("'")
    return out


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _parse_env_file(path)
    merged.update({k: v for k, v in updates.items() if v})
    lines = [
        "# OpenCOAT daemon LLM credentials — chmod 600; do not commit.",
        "# Load before `opencoat runtime up`:",
        "#   set -a && source ~/.opencoat/opencoat.env && set +a",
        "",
    ]
    for key in sorted(merged):
        val = merged[key]
        if not val:
            continue
        # Single-line values only; escape embedded newlines defensively.
        safe = val.replace("\n", "\\n").replace("\r", "")
        lines.append(f"{key}={safe}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    _chmod_secret(path)


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_yaml_llm(
    path: Path,
    *,
    llm: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _load_yaml_dict(path)
    old_llm = merged.get("llm")
    old_llm_dict = old_llm if isinstance(old_llm, dict) else {}
    merged["llm"] = {**old_llm_dict, **llm}
    text = yaml.safe_dump(merged, default_flow_style=False, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")
    if any(k in llm for k in ("api_key",)):
        _chmod_secret(path)


def _collect_interactive() -> tuple[str, Mode, dict[str, str], dict[str, Any]]:
    print("OpenCOAT — configure daemon LLM\n", file=sys.stderr)
    print(
        "The runtime resolves credentials in this order when provider is `auto`:\n"
        "  OPENAI_API_KEY → ANTHROPIC_API_KEY → AZURE_OPENAI_API_KEY + AZURE_OPENAI_DEPLOYMENT\n",
        file=sys.stderr,
    )
    print(
        "Choose how secrets are stored:\n"
        "  [1] env-file (default) — keys in ~/.opencoat/opencoat.env; YAML has no secrets\n"
        "  [2] inline — keys embedded in daemon.yaml (chmod 600); convenient but risky if copied\n",
        file=sys.stderr,
    )
    mode_raw = input("Storage mode [1]: ").strip() or "1"
    mode: Mode = "inline" if mode_raw == "2" else "env-file"

    print(
        "\nProvider for daemon YAML:\n"
        "  [1] auto (recommended)\n"
        "  [2] openai\n"
        "  [3] anthropic\n"
        "  [4] azure\n"
        "  [5] stub (no external LLM — hermetic / CI)\n",
        file=sys.stderr,
    )
    p_raw = input("Provider [1]: ").strip() or "1"
    provider_map = {"1": "auto", "2": "openai", "3": "anthropic", "4": "azure", "5": "stub"}
    provider = provider_map.get(p_raw, "auto")

    if mode == "inline" and provider == "auto":
        print(
            "configure llm: inline mode cannot be used with provider=auto "
            "(which credential would be embedded?). Choose env-file or an explicit provider.",
            file=sys.stderr,
        )
        sys.exit(2)

    env_updates: dict[str, str] = {}
    llm_inline: dict[str, Any] = {"provider": provider, "timeout_seconds": 30.0}

    if provider == "stub":
        llm_inline["provider"] = "stub"
        return provider, mode, env_updates, llm_inline

    def gp(prompt: str) -> str:
        return getpass.getpass(prompt)

    if provider in ("auto", "openai"):
        key = gp("OpenAI API key (Enter to skip): ").strip()
        if key:
            env_updates["OPENAI_API_KEY"] = key
        if provider == "openai" and not key:
            print("configure llm: openai provider requires an API key", file=sys.stderr)
            sys.exit(2)
        model = input("OpenAI model [gpt-4o-mini]: ").strip() or "gpt-4o-mini"
        if provider == "openai":
            llm_inline["model"] = model
        elif key:
            # auto + openai key: optional model still useful when forcing openai branch
            m = input("OPENAI_MODEL override (Enter to skip): ").strip()
            if m:
                env_updates["OPENAI_MODEL"] = m

    if provider in ("auto", "anthropic"):
        key = gp("Anthropic API key (Enter to skip): ").strip()
        if key:
            env_updates["ANTHROPIC_API_KEY"] = key
        if provider == "anthropic" and not key:
            print("configure llm: anthropic provider requires an API key", file=sys.stderr)
            sys.exit(2)
        if provider == "anthropic":
            model = (
                input("Anthropic model [claude-3-5-haiku-latest]: ").strip()
                or "claude-3-5-haiku-latest"
            )
            llm_inline["model"] = model
        elif key:
            m = input("ANTHROPIC_MODEL override (Enter to skip): ").strip()
            if m:
                env_updates["ANTHROPIC_MODEL"] = m

    if provider in ("auto", "azure"):
        key = gp("Azure OpenAI API key (Enter to skip): ").strip()
        endpoint = input("Azure endpoint URL (Enter to skip): ").strip()
        deployment = input("Azure deployment name (Enter to skip): ").strip()
        if provider == "azure":
            if not (key and endpoint and deployment):
                print(
                    "configure llm: azure provider requires API key, endpoint, and deployment",
                    file=sys.stderr,
                )
                sys.exit(2)
            env_updates["AZURE_OPENAI_API_KEY"] = key
            env_updates["AZURE_OPENAI_ENDPOINT"] = endpoint
            env_updates["AZURE_OPENAI_DEPLOYMENT"] = deployment
        elif key or endpoint or deployment:
            if not (key and endpoint and deployment):
                print(
                    "configure llm: for auto + Azure, provide all three: "
                    "API key, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT",
                    file=sys.stderr,
                )
                sys.exit(2)
            env_updates["AZURE_OPENAI_API_KEY"] = key
            env_updates["AZURE_OPENAI_ENDPOINT"] = endpoint
            env_updates["AZURE_OPENAI_DEPLOYMENT"] = deployment

    if provider == "auto" and not any(
        k in env_updates for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY")
    ):
        print(
            "configure llm: provider=auto needs at least one of: "
            "OPENAI_API_KEY, ANTHROPIC_API_KEY, or Azure triple",
            file=sys.stderr,
        )
        sys.exit(2)

    if mode == "inline" and provider != "stub":
        # Move secrets from env_updates into llm_inline for yaml
        if "OPENAI_API_KEY" in env_updates:
            llm_inline["api_key"] = env_updates.pop("OPENAI_API_KEY")
        if "ANTHROPIC_API_KEY" in env_updates:
            llm_inline["api_key"] = env_updates.pop("ANTHROPIC_API_KEY")
        if "AZURE_OPENAI_API_KEY" in env_updates:
            llm_inline["api_key"] = env_updates.pop("AZURE_OPENAI_API_KEY")
        if "AZURE_OPENAI_ENDPOINT" in env_updates:
            llm_inline["endpoint"] = env_updates.pop("AZURE_OPENAI_ENDPOINT")
        if "AZURE_OPENAI_DEPLOYMENT" in env_updates:
            llm_inline["deployment"] = env_updates.pop("AZURE_OPENAI_DEPLOYMENT")
        if env_updates:
            print(
                f"configure llm: inline mode cannot represent extra env keys {sorted(env_updates)} — "
                "dropping them (use env-file mode instead).",
                file=sys.stderr,
            )

    return provider, mode, env_updates, llm_inline


def _collect_non_interactive(
    args: argparse.Namespace,
) -> tuple[str, Mode, dict[str, str], dict[str, Any]]:
    provider = args.provider
    mode: Mode = "inline" if args.mode == "inline" else "env-file"
    env_updates: dict[str, str] = {}
    llm: dict[str, Any] = {"provider": provider, "timeout_seconds": float(args.timeout_seconds)}

    if provider == "stub":
        return provider, mode, env_updates, llm

    if args.model:
        llm["model"] = args.model
    if provider == "openai" and args.openai_base_url:
        llm["base_url"] = args.openai_base_url
    if provider == "anthropic" and args.anthropic_base_url:
        llm["base_url"] = args.anthropic_base_url

    if args.openai_api_key:
        env_updates["OPENAI_API_KEY"] = args.openai_api_key
    if args.openai_model_env:
        env_updates["OPENAI_MODEL"] = args.openai_model_env
    if args.anthropic_api_key:
        env_updates["ANTHROPIC_API_KEY"] = args.anthropic_api_key
    if args.anthropic_model_env:
        env_updates["ANTHROPIC_MODEL"] = args.anthropic_model_env
    if args.azure_api_key:
        env_updates["AZURE_OPENAI_API_KEY"] = args.azure_api_key
    if args.azure_endpoint:
        env_updates["AZURE_OPENAI_ENDPOINT"] = args.azure_endpoint
    if args.azure_deployment:
        env_updates["AZURE_OPENAI_DEPLOYMENT"] = args.azure_deployment

    if provider == "openai" and not args.openai_api_key:
        print("configure llm: --provider openai requires --openai-api-key", file=sys.stderr)
        sys.exit(2)
    if provider == "anthropic" and not args.anthropic_api_key:
        print("configure llm: --provider anthropic requires --anthropic-api-key", file=sys.stderr)
        sys.exit(2)
    if provider == "azure" and not (
        args.azure_api_key and args.azure_endpoint and args.azure_deployment
    ):
        print(
            "configure llm: --provider azure requires --azure-api-key, --azure-endpoint, "
            "--azure-deployment",
            file=sys.stderr,
        )
        sys.exit(2)
    if provider == "auto":
        has_openai = bool(args.openai_api_key)
        has_anthropic = bool(args.anthropic_api_key)
        has_azure = bool(args.azure_api_key and args.azure_endpoint and args.azure_deployment)
        if not (has_openai or has_anthropic or has_azure):
            print(
                "configure llm: --provider auto needs at least one credential set "
                "(openai, anthropic, or full azure triple)",
                file=sys.stderr,
            )
            sys.exit(2)

    if mode == "inline":
        if provider == "openai":
            llm["api_key"] = args.openai_api_key
        elif provider == "anthropic":
            llm["api_key"] = args.anthropic_api_key
        elif provider == "azure":
            llm["api_key"] = args.azure_api_key
            llm["endpoint"] = args.azure_endpoint
            llm["deployment"] = args.azure_deployment
        elif provider == "auto":
            print(
                "configure llm: --mode inline does not support --provider auto "
                "(ambiguous which key to embed). Use --mode env-file or pick an explicit provider.",
                file=sys.stderr,
            )
            sys.exit(2)
        env_updates.clear()

    return provider, mode, env_updates, llm


def _configure_llm(args: argparse.Namespace) -> int:
    yaml_path: Path = args.yaml.expanduser()
    env_path: Path = args.env.expanduser()

    if args.non_interactive:
        provider, _mode, env_updates, llm = _collect_non_interactive(args)
    else:
        if not sys.stdin.isatty():
            print(
                "configure llm: stdin is not a TTY — re-run with --non-interactive and the "
                "appropriate --openai-api-key / … flags, or attach a terminal.",
                file=sys.stderr,
            )
            return 2
        provider, _mode, env_updates, llm = _collect_interactive()

    # Strip empty optional llm keys for cleaner yaml
    llm_out = {k: v for k, v in llm.items() if v not in ("", None)}

    _write_yaml_llm(yaml_path, llm=llm_out)
    print(f"configure llm: wrote {yaml_path}", file=sys.stderr)

    wrote_any_env = False
    if env_updates:
        _write_env_file(env_path, env_updates)
        wrote_any_env = True
        print(f"configure llm: wrote {env_path}", file=sys.stderr)
    elif provider == "stub":
        print("configure llm: stub provider — no env file updates", file=sys.stderr)

    print("\n--- Next steps ---", file=sys.stderr)
    if wrote_any_env:
        print(
            f"  1. Load env vars into your shell (same terminal you use for `runtime up`):\n"
            f"       set -a && source {env_path} && set +a\n"
            f"  2. Start the daemon with the new config:\n"
            f"       opencoat runtime up --config {yaml_path} --pid-file ~/.opencoat/opencoat.pid\n"
            f"  3. Confirm the real provider:\n"
            f"       opencoat runtime status --config {yaml_path} --pid-file ~/.opencoat/opencoat.pid\n",
            file=sys.stderr,
        )
    else:
        print(
            f"  1. Start the daemon:\n"
            f"       opencoat runtime up --config {yaml_path} --pid-file ~/.opencoat/opencoat.pid\n"
            f"  2. Confirm LLM wiring:\n"
            f"       opencoat runtime status --config {yaml_path} --pid-file ~/.opencoat/opencoat.pid\n",
            file=sys.stderr,
        )
    print(
        "Full annotated sample: docs/config/daemon.yaml.example in the OpenCOAT repo.\n",
        file=sys.stderr,
    )
    return 0


def _register_llm(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "llm",
        help="guided setup for daemon LLM credentials (writes ~/.opencoat/daemon.yaml + opencoat.env)",
    )
    p.add_argument(
        "--yaml",
        dest="yaml",
        type=Path,
        default=_default_yaml_path(),
        help=f"path to daemon YAML to create/update (default: ~/{_DEFAULT_YAML_REL})",
    )
    p.add_argument(
        "--env",
        dest="env",
        type=Path,
        default=_default_env_path(),
        help=f"path to env file for API keys (default: ~/{_DEFAULT_ENV_REL}; env-file mode only)",
    )
    p.add_argument(
        "--mode",
        choices=("env-file", "inline"),
        default="env-file",
        help="env-file: keys in opencoat.env (default); inline: secrets embedded in YAML (chmod 600)",
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="read credentials from flags instead of prompts",
    )
    p.add_argument(
        "--provider",
        choices=("auto", "openai", "anthropic", "azure", "stub"),
        default="auto",
        help="daemon llm.provider (non-interactive default: auto)",
    )
    p.add_argument(
        "--timeout-seconds", type=float, default=30.0, help="llm.timeout_seconds written to YAML"
    )
    p.add_argument(
        "--model", default=None, help="llm.model in YAML (openai/anthropic explicit providers)"
    )
    p.add_argument(
        "--openai-api-key", default=os.environ.get("OPENAI_API_KEY"), help="non-interactive"
    )
    p.add_argument(
        "--openai-model-env", default=None, help="set OPENAI_MODEL in env file (auto mode)"
    )
    p.add_argument(
        "--anthropic-api-key", default=os.environ.get("ANTHROPIC_API_KEY"), help="non-interactive"
    )
    p.add_argument("--anthropic-model-env", default=None, help="set ANTHROPIC_MODEL in env file")
    p.add_argument(
        "--azure-api-key", default=os.environ.get("AZURE_OPENAI_API_KEY"), help="non-interactive"
    )
    p.add_argument(
        "--azure-endpoint", default=os.environ.get("AZURE_OPENAI_ENDPOINT"), help="non-interactive"
    )
    p.add_argument("--azure-deployment", default=os.environ.get("AZURE_OPENAI_DEPLOYMENT"), help="")
    p.add_argument(
        "--openai-base-url", default=None, help="llm.base_url for OpenAI-compatible gateways"
    )
    p.add_argument(
        "--anthropic-base-url", default=None, help="llm.base_url when provider=anthropic"
    )
    p.set_defaults(func=_configure_llm)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "configure",
        help="interactive configuration helpers (LLM credentials, …)",
    )
    inner = p.add_subparsers(dest="configure_target", required=True)
    _register_llm(inner)


__all__ = ["register"]
