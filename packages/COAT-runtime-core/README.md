# COAT-runtime-core

L2 pure-logic layer of the COAT Runtime. No I/O, no external services — every
side-effecting concern is expressed as a [Port](COAT_runtime_core/ports/)
that callers wire to a real adapter.

Layout mirrors v0.1 §20 / v0.2 §4.2:

```text
COAT_runtime_core/
├── runtime.py           # COATRuntime facade
├── concern/             # extractor / separator / builder / verifier / lifecycle / vector / model
├── joinpoint/           # 8-level model + catalog
├── pointcut/            # matcher + compiler + 11 strategies
├── advice/              # generator + templates + 11 advice types
├── weaving/             # weaver + 11 operations + targets
├── copr/                # parser / tokenizer / span_segmenter / renderer
├── coordinator/         # Concern Vector generation, top-K, budget, priority
├── resolver/            # conflict / dedupe / escalation
├── dcn/                 # network / 13 relations / activation_history / evolution
├── meta/                # 8 meta governance capabilities
├── loops/               # turn / event / heartbeat
├── ports/               # six hexagonal ports
└── observability/       # metrics / tracing / logging
```

In M0 every module is a typed skeleton — methods exist with their final
signatures and raise `NotImplementedError`. M1 fills these in with stub
implementations so the in-proc happy path runs end-to-end.
