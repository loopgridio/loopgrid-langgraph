# LoopGrid LangGraph v0.1.0 — RC3 validation ledger (2026-10-12)

## Verified on user's Windows system for earlier candidates

- Config-fixed pre-RC2: **55 passed**, real installed LangGraph `StateGraph`, `InMemorySaver`, `interrupt` / `Command(resume)` passed. Both local Core 0.8.1 E2Es passed with signed verification valid. These results **do not count as RC3 Core validation**.
- Hardened RC2: Windows Python 3.12, LangGraph 1.2.14, `langgraph-checkpoint-sqlite` 3.1.1. **67 passed**, `langgraph_runtime_e2e.py` **PASS**, `persistent_langgraph_e2e.py` **PASS** (two restarts, one sandbox tool call, no duplicate args in `loopgrid` scope).
- **RC2 Core FAIL:** both `real_core_e2e.py` and `native_core_langgraph_e2e.py` raised `EvidenceInvalid: Signed decision identity, authority or context changed`. RC2's new signed-metadata comparison was comparing Core's redacted typed SHA-256 fields with original strings. This is an adapter comparison bug, not evidence of a Core integrity failure.

## RC3 — verified locally (isolated Python 3.13.5, no installed LangGraph runtime)

- **77/77 tests passed** with `PYTHONPATH=src:tests python -m pytest -q`. Added ten regression cases (compared with RC2's 67) for typed redacted commitments, replay identity validation and tampering/mismatch.
- Coverage via `--cov=loopgrid_langgraph --cov-fail-under=90`: **90.36%**, CI gate passed.
- The compatibility matcher was checked against a historical exported real-Core `decision_created` evidence record; agent/authority/model/context values and canonical-JSON SHA-256 redaction commitments all matched. This does not constitute a fresh live-Core run.
- Python wheel built via `pip wheel --no-deps --no-build-isolation` in this isolated environment.
- Fix is limited to signed metadata comparison; policy/review/tool dispatch/core event wire contract remain unchanged.

## RC3 — verified on user Windows system (2026-10-12)

- `python -m pip install -e ".[test,persistence-test]"`: installed successfully under Python 3.12.
- `python -m pytest -q`: **77 passed in 1.46s**.
- Real LangGraph `StateGraph + InMemorySaver + interrupt + Command(resume)` script: **PASS**; one synthetic tool execution, with observed checkpoint interruption and resumption.
- `SqliteSaver` persistent restart/resume script: **PASS**; two restarts, one synthetic tool execution, no duplicate raw arguments in LoopGrid scope. Core in this test is explicitly **synthetic**.
- `real_core_e2e.py`: **PASS**, against local LoopGrid Core `0.8.1-design-partner`, workspace verification `true`, failures `[]`, two synthetic executions, lifecycle `evidence_complete`, applicable coverage `100`, no real money. This script does **not** invoke the LangGraph SDK.
- `native_core_langgraph_e2e.py`: **PASS**, actual installed LangGraph `StateGraph` + local LoopGrid Core, policy, signed human review, interrupt/resume and replay protection; signed workspace verification `true`, failures `[]`, two synthetic executions, lifecycle `evidence_complete`, applicable coverage `100`, no real money.
- The earlier RC2 signed-redaction mismatch did **not** recur.

## Remaining publication gates

1. Build a **fresh** wheel and sdist; run `scripts/check_dist.py` and `python -m twine check dist\*` (PowerShell).
2. Install the **built wheel** into a new isolated venv without editable mode, allowing dependency resolution; import public classes and confirm package metadata.
3. Push the **validated RC3 code** to a new `loopgridio/loopgrid-langgraph` repository and require all hosted GitHub CI checks on Python 3.10/3.12/3.13 across Ubuntu/Windows/macOS, plus separate clean-wheel consumer job.
4. Tag/publish release `v0.1.0` only after CI, prepare PyPI Trusted Publisher OIDC and enable opt-in release workflow; verify the first public `pip install` from PyPI.
5. Production host controls for signed reviewer identity, remote multi-worker durable leases and authoritative external business outcome verification remain **host responsibilities**. SQLite lease is single-host only; async guarded callbacks are not supported in v0.1.0.

**Release decision: PASS on native/runtime/real-Core local validation; HOLD public distribution until remaining release gates pass.**
