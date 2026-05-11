# Examples

End-to-end usage of the COAT Runtime.

| # | Folder | Lands in |
| --- | --- | --- |
| 01 | `01_simple_chat_agent/` | M1 (in-proc happy path) |
| 02 | `02_coding_agent_demo/` | M2 (real LLM) |
| 03 | `03_persistent_agent_demo/` | M3 (sqlite + JSONL session) |
| 03 (research) | `03_research_agent_demo/` | M2 / M3 (placeholder) |
| 04 | `04_openclaw_with_runtime/` | M5 |
| 05 | `05_langgraph_with_runtime/` | M7 |
| 06 | `06_long_running_daemon/` | M4 (PR-23) — programmatic Daemon ↔ HTTP JSON-RPC end-to-end |

Each example contains a `README.md` with the user story, a runnable
`main.py`, and a frozen transcript so we can diff future runs.
