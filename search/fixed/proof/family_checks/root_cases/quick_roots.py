"""Fresh complete-library root exclusions. No archived result is an input.

Rebuilds every input from paid seeds. No historical circuit or certificate
is accepted as an input. A NAND4 run also emits an independent cover proof.
"""
from ...runtime import run as _run, fail as _fail
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
HERE = Path(__file__).resolve().parent
from ...model import D, S
from ...family_checks.library import build, quote
from ...family_checks.audit_library import audit
from ...family_checks.root_cases.cover_certificate import emit, verify

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--nand4', action='store_true', help='Also generate the complete NAND4 child coverage basis.')
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pwsh = shutil.which('pwsh')
    if not pwsh:
        raise SystemExit('PowerShell 7 is required')
    target = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    start = time.time()
    (out / 'status.json').write_text(json.dumps(dict(status='RUNNING', previous_result_files_read=0)), encoding='utf-8')
    fresh = out / 'fresh_library'
    fresh.mkdir()
    image = build(100883, fresh, pwsh)
    settings = out / 'settings.json'
    settings.write_text(json.dumps(dict(names=list(D), costs=list(D.values()))), encoding='utf-8')
    script = out / 'query.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n" + f"Add-Type -Path @({quote(HERE.parent / 'FullImage.cs')}, {quote(HERE / 'RootQueries.cs')})\n" + f"[RootQueries]::Run({quote(image)}, {quote(out / 'roots.json')}, " + f"{quote(settings)}, [UInt64]::Parse('{target}'), " + ('$true' if a.nand4 else '$false') + ')\n', encoding='utf-8')
    with (out / 'native.log').open('w', encoding='utf-8') as log:
        _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    rows = json.loads((out / 'roots.json').read_text(encoding='utf-8'))
    audits = [audit(folder) for folder in sorted(fresh.iterdir()) if folder.is_dir() and folder.name.isdigit()]
    cover_report = None
    if a.nand4 and next((r for r in rows if r['root'] == 'NAND4'))['status'] == 'UNSAT':
        cert = out / 'nand4_certificate'
        cert.mkdir()
        emit(out / 'roots.json.nand4_basis.json', cert, 4)
        cover_report = verify(cert)
        (cert / 'certificate.json').write_text(json.dumps(cover_report, indent=2), encoding='utf-8')
    status = 'SELECTED_ROOTS_EXCLUDED' if all((r['status'] == 'UNSAT' for r in rows)) else 'SELECTED_ROOT_COUNTEREXAMPLE'
    (out / 'status.json').write_text(json.dumps(dict(status=status, root_deadline_fs=157297, coordinate=2, roots=rows, seconds=time.time() - start, previous_result_files_read=0, library_witness_audits=audits, nand4_cover_certificate=cover_report, global_lower_bound_proved=False), indent=2), encoding='utf-8')
    print(status)
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
