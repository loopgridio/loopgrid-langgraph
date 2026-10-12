# GitHub / PyPI v0.1.0 release record (completed 2026-10-12)

**Published identity**

- GitHub owner/repository: `loopgridio/loopgrid-langgraph` (created)
- PyPI package: `loopgrid-langgraph` (published)
- Distribution/import: `pip install loopgrid-langgraph` / `import loopgrid_langgraph`
- First tag: `v0.1.0` (tagged after all 10 CI jobs passed)
- Public repo release title: `LoopGrid LangGraph Integration v0.1.0`
- License: Apache-2.0

**Publishing procedure (completed for v0.1.0; reference for future releases)**

1. Confirm Windows `pytest`, installed LangGraph native StateGraph E2E, combined Docker Core E2E, signed evidence and wheel/sdist checks.
2. Inspect README examples, package manifest, `.gitignore`, tokens and private evidence files. `git add .; git diff --cached --name-only; git diff --cached --check`.
3. Created a public repository under `loopgridio`, pushed initial source, then pushed the 12-test coverage supplement (final tag commit `24327c4`).
4. Check **all** matrix jobs under `.github/workflows/tests.yml`. Resolve failures without weakening safety invariants.
5. `git tag -a v0.1.0 -m "LoopGrid LangGraph Integration v0.1.0"; git push origin v0.1.0`.
6. Created a **PyPI Pending Trusted Publisher** (subsequently activated on first upload) pointing to GitHub owner `loopgridio`, repo `loopgrid-langgraph`, workflow `release.yml`, environment `pypi`. Exact names and account permission are required. Create the matching GitHub environment before releasing.
7. Publish GitHub Release `v0.1.0`; monitor PyPI OIDC publish workflow, then `pip install loopgrid-langgraph==0.1.0` in a fresh environment and test public import and native example.
8. Update canonical `loopgrid.io` website, integrations index, docs, sitemap and `llms.txt`, then seek the correct LangGraph/LangChain ecosystem listing; never claim official verified status in advance.

**Security:** No long-lived PyPI API tokens. Release workflow has `id-token: write` scoped to publish job, checks tag/package version, and uses Trusted Publishing. For a future release, do not trigger publication before its validation gates pass.

**Post-release follow-up:** record a fresh public PyPI index install, deploy the website guide, and seek ecosystem discoverability without claiming official approval.
