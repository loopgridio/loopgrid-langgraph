# GitHub / PyPI release plan (do not publish until real native gates pass)

**Proposed public identity**

- GitHub owner/repository: `loopgridio/loopgrid-langgraph` (verify it does not already exist)
- PyPI package: `loopgrid-langgraph` (verify name availability and publisher account)
- Distribution/import: `pip install loopgrid-langgraph` / `import loopgrid_langgraph`
- First tag: `v0.1.0` (ONLY after cross-platform green CI)
- Public repo release title: `LoopGrid LangGraph Integration v0.1.0`
- License: Apache-2.0

**Publishing sequence**

1. Confirm Windows `pytest`, installed LangGraph native StateGraph E2E, combined Docker Core E2E, signed evidence and wheel/sdist checks.
2. Inspect README examples, package manifest, `.gitignore`, tokens and private evidence files. `git add .; git diff --cached --name-only; git diff --cached --check`.
3. Create a NEW public empty GitHub repository under `loopgridio`; push source with commit `Initial release of LoopGrid LangGraph integration v0.1.0`.
4. Check **all** matrix jobs under `.github/workflows/tests.yml`. Resolve failures without weakening safety invariants.
5. `git tag -a v0.1.0 -m "LoopGrid LangGraph Integration v0.1.0"; git push origin v0.1.0`.
6. Create a **PyPI Pending Trusted Publisher** for the package (the package is not yet registered) pointing to GitHub owner `loopgridio`, repo `loopgrid-langgraph`, workflow `release.yml`, environment `pypi`. Exact names and account permission are required. Create the matching GitHub environment before releasing.
7. Publish GitHub Release `v0.1.0`; monitor PyPI OIDC publish workflow, then `pip install loopgrid-langgraph==0.1.0` in a fresh environment and test public import and native example.
8. Update canonical `loopgrid.io` website, integrations index, docs, sitemap and `llms.txt`, then seek the correct LangGraph/LangChain ecosystem listing; never claim official verified status in advance.

**Security:** Do not embed long-lived PyPI API tokens. Release workflow has `id-token: write` scoped to publish job, checks tag/package version, and uses Trusted Publishing. Do not create the official tag or trigger the workflow while validation remains pending.
