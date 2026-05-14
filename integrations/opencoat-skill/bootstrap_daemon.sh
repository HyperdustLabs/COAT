#!/usr/bin/env bash
# OpenCOAT — post-install: start daemon + register OS autostart (LaunchAgent / systemd user).
# Intended to run right after `pipx install opencoat-runtime` + `pipx inject … opencoat-runtime-host`.
set -euo pipefail

mkdir -p "${HOME}/.opencoat"

echo "==> opencoat runtime up"
opencoat runtime up

echo "==> opencoat runtime status"
opencoat runtime status

case "$(uname -s)" in
Darwin | Linux)
  echo "==> opencoat service install (login / boot autostart)"
  opencoat service install
  echo "==> opencoat service status"
  opencoat service status || true
  ;;
*)
  echo "==> skip opencoat service install (unsupported OS: $(uname -s))"
  ;;
esac

echo "Done. Manage with: opencoat service stop|start|restart|uninstall  ·  opencoat runtime status|down"
