"""Check native accelerated kernels against exhaustive small-instance oracles."""
from ...runtime import run as _run, fail as _fail
from pathlib import Path
import argparse, subprocess, shutil, sys, os
from ...family_checks.library import quote

def main():
    H = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    src = [H.parent / 'FullImage.cs', H / 'RootQueries.cs', H / 'LargePairsJoin.cs', H / 'Residual.cs', H / 'KernelChecks.cs']
    ps = out / 'run.ps1'
    ps.write_text("$ErrorActionPreference='Stop'\nAdd-Type -Path @(" + ','.join(map(quote, src)) + f')\n[KernelChecks]::Run({quote(out)})\n', encoding='utf-8')
    with (out / 'native.log').open('w') as log:
        _run([shutil.which('pwsh'), '-NoProfile', '-File', str(ps)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    print((out / 'report.json').read_text())
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
