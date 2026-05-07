# COAT-runtime-cli

`COATr` — command-line interface for the COAT Runtime. Talks to a local
daemon (or in-proc runtime) over the host SDK transports.

```bash
COATr runtime up
COATr concern list --kind concern
COATr dcn export --format dot
COATr replay session.jsonl
```

M0 ships only a skeleton dispatcher; M4 wires the real subcommands.
