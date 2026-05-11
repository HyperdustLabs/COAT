# COAT-runtime-cli

`COATr` — command-line interface for the COAT Runtime. Talks to a local
daemon (or in-proc runtime) over the host SDK transports.

`COATr replay session.jsonl` replays a JSONL session recorded via
`COAT_runtime_storage.jsonl.SessionJsonlRecorder` (M3). Other
subcommands remain stubs until M4.

```bash
COATr runtime up
COATr concern list --kind concern
COATr dcn export --format dot
COATr replay session.jsonl
```

M0 shipped a skeleton dispatcher; M3 adds replay; M4 wires the remaining subcommands.
