"""Cross-platform package artifact verification and optional Twine check."""
from __future__ import annotations
import sys,tarfile,zipfile,subprocess
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 build validation
    import tomli as tomllib

root=Path(__file__).resolve().parents[1]
meta=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']
name=meta['name'].replace('-','_')
version=meta['version']
built=root/'dist'
wheels=list(built.glob(f'{name}-{version}-*.whl'))
sdists=list(built.glob(f'{name}-{version}.tar.gz'))
assert len(wheels)==len(sdists)==1,(wheels,sdists)
with zipfile.ZipFile(wheels[0]) as z:
    files=z.namelist()
    assert len(files)>=9 and all('secret' not in p.lower() and '.env' not in p for p in files)
    assert all(f'loopgrid_langgraph/{f}' in files for f in ('__init__.py','core.py','integration.py','observability.py','leases.py'))
    assert not any('/tests/' in p or '/scripts/' in p or p.endswith('.pem') for p in files)
with tarfile.open(sdists[0],mode='r:gz') as z:
    names=z.getnames()
    assert any(n.endswith('/tests/fakes.py') for n in names)
    assert any(n.endswith('/scripts/langgraph_runtime_e2e.py') for n in names)
    assert any(n.endswith('/scripts/persistent_langgraph_e2e.py') for n in names)
    assert any(n.endswith('/examples/refund_checkpoint.py') for n in names)
print(f'PASS: wheel ({len(files)} files) and sdist ({len(names)} files), safe source contents')
try:
    import twine  # noqa: F401
except ImportError:
    print('NOTE: Twine unavailable locally; python -m twine check remains a required Windows/CI gate')
else:
    subprocess.check_call([sys.executable,'-m','twine','check',str(wheels[0]),str(sdists[0])])
