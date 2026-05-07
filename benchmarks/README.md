# Benchmarks

Microbenchmarks for the hot paths. M2+ delivers actual runs.

| File | Measures |
| --- | --- |
| `concern_extraction_bench.py` | LLM-driven extraction throughput |
| `pointcut_match_bench.py` | matcher latency over 1k pointcuts × 1k joinpoints |
| `weaving_bench.py` | weaver throughput at the configured budget |
