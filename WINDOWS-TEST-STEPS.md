# LoopGrid LangGraph v0.1.0 RC3 (Core redaction fix) — Windows validation

Unzip this **complete package into a new folder** (don't overlay the older v0.1.0 candidate). Open PowerShell at the folder with `pyproject.toml`. Python 3.12 recommended.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test,persistence-test]"
python -m pytest -q
python .\scripts\langgraph_runtime_e2e.py
python .\scripts\persistent_langgraph_e2e.py
```

Expected unit result: **77 passed**. The first script is a real installed LangGraph `StateGraph`+in-memory checkpoint test. The second is **a separate real SDK SQLite persistent checkpoint test**: interrupt, close/reopen checkpointer, signed synthetic review, resume, close/reopen again, and replay prevention. Both are **synthetic Core** tests and perform no payment/API side effects. The SQLite extra `langgraph-checkpoint-sqlite` is for testing only.

Start LoopGrid Core in another shell if it isn't running:

```powershell
docker start loopgrid-dify-test
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Then from the project's active virtual environment:

```powershell
$env:LOOPGRID_BASE_URL = "http://127.0.0.1:8000"
python .\scripts\real_core_e2e.py
python .\scripts\native_core_langgraph_e2e.py
```

These create separate disposable workspaces and synthetic policies. **RC3 already passed both real-Core tests on Windows (2026-10-12)** after correcting RC2's typed redaction-commitment comparison. A new consumer should still rerun them when possible. Expected Core output includes `signed_workspace_verification: true`, `failures: []`, `sandbox_executions: 2`, `real_money_moved: false`; combined native script prints `PASS: REAL installed LangGraph StateGraph + local LoopGrid Core`.

Next build the distributions from a clean working directory:

```powershell
python -m build
python .\scripts\check_dist.py
python -m twine check dist\*
```

`check_dist.py` expects exactly one wheel and one sdist. A **separate new venv** must still successfully install the produced wheel with dependencies and import `LangGraphBridge`, `CoreClient` and `LocalSqliteDispatchLease`. Hosted GitHub Actions matrix must pass before tagging/publishing.

Do **not** paste service keys or signer private keys. See `VALIDATION.md` and `docs/WORKER-RECOVERY-AND-PRIVACY.md` for exact trust boundaries.
