# Changelog

## 0.1.0 — Pre-publication candidate (2026-10-12)

- Native LangGraph `StateGraph` proposal, guarded action and verification nodes.
- Persisted decision correlation through stable operation ID and graph thread/checkpoint state.
- Versioned LoopGrid Core policy provenance, human-review pause/resume, signed check before dispatch.
- SHA-256 redacted arguments and privacy-safe model/output commitments.
- Conservative cross-restart no-replay semantics, explicit outcome recording and read-only graph callbacks.
- Unit/security tests, isolated real-Core E2E, independent offline signature verification, cross-platform CI template and packaging metadata.

**Not published:** RC3 Windows real-Core rerun passed on 2026-10-12. Full packaging/consumer install, hosted CI and public PyPI remain release gates. See VALIDATION.md.

## Pre-publication correction — 2026-10-12

- Corrected LangGraph native node injection typing to `config: RunnableConfig` across proposal, guarded execution and verify nodes after real 1.2.14 SDK exposed the `config: dict` incompatibility.
- Added regression coverage for generated node annotations; source remains pre-publication `0.1.0`.

### Release candidate hardening (unpublished; no version bump)

- Added host-supplied cross-worker `dispatch_lease` protocol with `require_dispatch_lease=True` fail-closed deployment option; single-host `LocalSqliteDispatchLease` reference.
- Refused duplicate Core `tool_requested` idempotency responses and any signed rejection (including reject-then-approve), and strict agent/authority/context/model identity binding for signed decision replay.
- Native graph proposal scopes no longer duplicate raw tool arguments in checkpoints; keep SHA-256 commitment, rederive arguments from host state.
- Reject async guarded callbacks (v0.1.0 sync-only) and avoid unawaited coroutine leaks.
- Added two-worker and spawned-process lock regressions, privacy/replay tests and persistent LangGraph SqliteSaver restart/resume E2E.
- Retained existing v0.1.0 Core wire/event contract. Validation gates still apply before publishing.

### RC3 Core redaction compatibility fix (unpublished; no version bump)

- `Core 0.8.1-design-partner` returns `{redacted:true,sha256:<canonical-json-hash>,type:"str"}` for selected signed creation fields such as `model.name` and `context.prompt_version` in `privacy_mode=redacted`.
- Correctly validate typed, signed SHA-256 commitment envelopes recursively, including type, digest, exact keys, and all unredacted fields. **Do not bypass** agent/authority/context/model identity checks.
- Preserved exact signed proposed-action, current-policy, review, Core tool reservation and no-replay enforcement. No wire-format changes.
- Added 10 regression cases for legitimate redaction and mismatched/malformed commitments. **77/77** local tests passed, **90%+** statement coverage; exported prior real-Core evidence fixture also matched.
- RC2's two real-Core E2Es failed on strict raw-value comparison; **RC3 live-Core rerun passed** on Windows for both standalone Core and real LangGraph + Core. Signed verification valid, zero failures and synthetic tool execution only.
