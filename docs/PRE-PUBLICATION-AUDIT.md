# LoopGrid LangGraph — pre-publication audit (2026-10-12 hardening)

**Decision: HOLD publication until packaging, clean consumer install and hosted CI pass.**
The user completed the RC3 native and Core E2E suite on Windows on 2026-10-12.
Those RC3 results supersede the older candidate and RC2 failure records.

## Proven previous baseline (user Windows PowerShell, 2026-10-12)
- 55/55 previous automated tests passed on Python 3.12.6.
- Real installed LangGraph 1.2.14 `StateGraph + InMemorySaver + interrupt + Command(resume)` passed.
- Real local LoopGrid Core 0.8.1 test: allow/block/review, valid signed workspace verification.
- Combined installed LangGraph + Core E2E: valid signed verification, two synthetic dispatches, no real money.

## Hardened RC3 (native/runtime gates now passed on Windows)
- New host dispatch lease, reference same-host SQLite serializing lease and cross-process test.
- Duplicate reservation refusal and signed rejection finality.
- Duplicate raw argument removal from `loopgrid` graph scope, NOT from host graph state.
- Sync-only callback detection and persistent LangGraph SQLite restart script.
- RC3 unit/security tests: 77/77 passed on Windows; Core E2Es passed, signed verification valid, 100% applicable coverage; see VALIDATION.md.

## Publication gates
- **Completed:** LangGraph 1.2.14 runtime, persistent SqliteSaver, standalone Core and combined LangGraph + Core rerun on Windows.
- **Pending:** Fresh wheel/sdist build, Twine check, isolated non-editable install and hosted GitHub 3-OS CI.
- Reviewer authentication, production multi-worker leasing, and privacy are host responsibilities.
- Do not claim LangGraph endorsement or independent real-world business outcome proof.
