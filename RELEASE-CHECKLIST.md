# LoopGrid LangGraph v0.1.0 — Release checklist

- [x] Framework-native extension architecture researched (LangGraph 1.2.14)
- [x] Core evidence contract and other integration standards reviewed
- [x] Immutable, correlated proposal; deny/review/allow and signed-state guard
- [x] Synthetic unit and security tests passing (77 in RC3 local candidate, 2026-10-12)
- [x] Separate isolated LoopGrid Core 0.8.1 E2E with valid workspace signing
- [x] Independent trusted-key signed ledger verification; legacy attestation warning recorded
- [x] Real installed LangGraph StateGraph interrupt/resume E2E (user Windows, original corrected candidate)
- [x] Combined installed LangGraph and real LoopGrid Core E2E (user Windows, original corrected candidate)
- [x] RC3 Windows: 77/77 tests, installed LangGraph interrupt/resume, persistent SqliteSaver restart and **BOTH** Core E2Es all passed (2026-10-12; Core signing valid, zero failures, synthetic only)
- [ ] Final standard RC3 wheel/sdist build, `twine check`, package contents and clean consumer install
- [ ] GitHub repo public under `loopgridio`, full cross-platform CI green
- [x] Add host lease protocol, single-host SQLite lock sample and cross-process unit tests
- [ ] Validate production host durable, fenced multi-worker leasing and identity provider (host responsibility)
- [ ] Tag tested commit `v0.1.0` and create GitHub Release
- [ ] Activate PyPI trusted publisher (workflow `release.yml`, GitHub environment `pypi`) and publish
- [ ] Verify clean public PyPI installation and example
- [ ] Website integration, docs/index/sitemap and community ecosystem review

No completed checkbox implies marketplace endorsement or independent verification of business truth.
