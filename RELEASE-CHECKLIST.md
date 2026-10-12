# LoopGrid LangGraph v0.1.0 — Release checklist

- [x] Framework-native extension architecture researched (LangGraph 1.2.14)
- [x] Core evidence contract and other integration standards reviewed
- [x] Immutable, correlated proposal; deny/review/allow and signed-state guard
- [x] Synthetic unit and security tests passing (89 after coverage hardening, 2026-10-12)
- [x] Separate isolated LoopGrid Core 0.8.1 E2E with valid workspace signing
- [x] Independent trusted-key signed ledger verification; legacy attestation warning recorded
- [x] Real installed LangGraph StateGraph interrupt/resume E2E (user Windows, original corrected candidate)
- [x] Combined installed LangGraph and real LoopGrid Core E2E (user Windows, original corrected candidate)
- [x] RC3 Windows: 77/77 tests, installed LangGraph interrupt/resume, persistent SqliteSaver restart and **BOTH** Core E2Es all passed (2026-10-12; Core signing valid, zero failures, synthetic only)
- [x] Final RC3 wheel/sdist build, `twine check`, package contents and clean non-editable wheel consumer install
- [x] GitHub repo public under `loopgridio`, all 9 OS/Python matrix jobs and clean-wheel consumer job green (commit `24327c4`)
- [x] Add host lease protocol, single-host SQLite lock sample and cross-process unit tests
- [ ] Validate production host durable, fenced multi-worker leasing and identity provider (host responsibility)
- [x] Tag tested commit `v0.1.0` and create GitHub Release
- [x] Activate PyPI trusted publisher (workflow `release.yml`, GitHub environment `pypi`) and publish using OIDC
- [ ] Verify explicit no-cache public PyPI installation and example (GitHub OIDC upload succeeded; public index install separately pending)
- [ ] Website integration, docs/index/sitemap and community ecosystem review

No completed checkbox implies marketplace endorsement or independent verification of business truth.
