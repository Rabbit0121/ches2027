"""Two phases: finish concrete structural catalogues, then expand inputs."""
from .runtime import run as _run, fail as _fail
import argparse, json, os, shutil, struct, subprocess, time
from pathlib import Path
from .model import D, PI, M
from .structure_catalogue import catalogue
H = Path(__file__).resolve().parent

from .runtime import quote

def plan(bound, out):
    budgets = []
    b = bound
    while b >= 0:
        budgets.append(b)
        if b < 2 * min(D.values()):
            break
        b -= min(D.values())
    entries = []
    for b in reversed(budgets):
        folder = out / str(b)
        folder.mkdir()
        entries.append(catalogue(b, folder / 'structures.json'))
    r = dict(status='STRUCTURE_PHASE_COMPLETE', requested_bound_fs=bound, catalogues=entries, truth_tables_evaluated=0)
    (out / 'structure_phase.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    return list(reversed(budgets))

def build(bound, out, pwsh=None):
    pwsh = pwsh or shutil.which('pwsh')
    assert pwsh
    budgets = plan(bound, out)
    previous = None
    for b in budgets:
        folder = out / str(b)
        seed = [(PI[f'x{i}'] if g == 'BUF' else M ^ PI[f'x{i}'], D[g], i, g) for i in range(6) for g in ('BUF', 'INV') if D[g] <= b]
        dest = folder / 'image.bin'
        if previous is None:
            with dest.open('wb') as f:
                f.write(struct.pack('<II', 0, len(seed)))
                for v, t, i, g in seed:
                    f.write(struct.pack('<Qiiiiii', v, t, -2, i, list(D).index(g), -1, -1))
            status = dict(states=len(seed), enumerated_structures=len({g for _, _, _, g in seed}), processed_structures=len({g for _, _, _, g in seed}))
        else:
            inp = folder / 'input.bin'
            with previous.open('rb') as r, inp.open('wb') as w:
                found, n = struct.unpack('<II', r.read(8))
                assert found == 0
                w.write(struct.pack('<I', n + len(seed)))
                for _ in range(n):
                    f, t, *_ = struct.unpack('<Qiiiiii', r.read(32))
                    w.write(struct.pack('<QI', f, t))
                assert not r.read(1)
                for f, t, _, _ in seed:
                    w.write(struct.pack('<QI', f, t))
            script = folder / 'run.ps1'
            script.write_text("$ErrorActionPreference='Stop'\n" + f"Add-Type -Path {quote(H / 'StructureImage.cs')}\n[StructureImage]::Run({quote(inp)},{quote(folder / 'structures.json')},{quote(dest)},{b},{b - min(D.values())})\n", encoding='utf-8')
            with (folder / 'native.log').open('w') as log:
                _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
            status = json.loads(Path(str(dest) + '.status.json').read_bytes())
            assert status['status'] == 'COMPLETE_INPUT_EXPANSION_OF_ENUMERATED_STRUCTURES' and status['processed_structures'] == status['enumerated_structures']
        assert dest.stat().st_size == 8 + 32 * status['states']
        certificate = dict(status='COMPLETE_FROM_PAID_SEEDS', method='STRUCTURES_FIRST_INPUTS_SECOND', bound_fs=b, functions=status['states'], enumerated_structures=status['enumerated_structures'], processed_structures=status['processed_structures'], previous_result_files_read=0)
        (folder / 'certificate.json').write_text(json.dumps(certificate, indent=2), encoding='utf-8')
        previous = dest
        print(json.dumps(certificate), flush=True)
    return previous
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument('--bound-fs', type=int, default=100883)
        p.add_argument('--output', required=True, type=Path)
        a = p.parse_args()
        out = a.output.resolve()
        out.mkdir(parents=True, exist_ok=False)
        start = time.time()
        dest = build(a.bound_fs, out)
        (out / 'run.json').write_text(json.dumps(dict(status='COMPLETE_STRUCTURES_FIRST_DOMAIN', bound_fs=a.bound_fs, image=str(dest.relative_to(out)), seconds=time.time() - start), indent=2), encoding='utf-8')
    except Exception as error:
        _fail(error)
