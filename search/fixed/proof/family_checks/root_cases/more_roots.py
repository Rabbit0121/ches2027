"""Fresh exact AOI22/OAI22 and irreducible terminal-inverter branches."""
from ...runtime import run as _run, fail as _fail
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
from ...model import D, S
from ...family_checks.library import build, quote

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pwsh = shutil.which('pwsh')
    assert pwsh
    target = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    start = time.time()
    report = dict(status='RUNNING', global_lower_bound_proved=False, root_deadline_fs=157297)

    def save():
        (out / 'status.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    lib = out / 'fresh_library'
    lib.mkdir()
    image = build(102868, lib, pwsh)
    src = [HERE.parent / 'FullImage.cs', HERE / 'RootQueries.cs', HERE / 'DirectRoots.cs', HERE / 'LargePairsJoin.cs', HERE / 'Residual.cs']
    script = "$ErrorActionPreference='Stop'\nAdd-Type -Path @(" + ','.join(map(quote, src)) + ')\n'
    script += f"[DirectRoots]::Run({quote(image)},{quote(out / 'direct.json')},[UInt64]::Parse('{target}'))\n"
    jobs = []
    for name, gate, inverted in [('AOI22', 'AOI22', False), ('OAI22', 'OAI22', True), ('INV_AOI22', 'AOI22', False), ('INV_OAI22', 'OAI22', True)]:
        cut = 157297 - D[gate] - (D['INV'] if name.startswith('INV_') else 0)
        want = ~target & (1 << 64) - 1 if name.startswith('INV_') else target
        forbidden = ~want & (1 << 64) - 1 if inverted else want
        img = out / (name + '.image')
        pairs = out / (name + '.pairs')
        result = out / (name + '.json')
        script += f'[DirectRoots]::Extract({quote(img)},{cut})\n'
        flag = '$true' if inverted else '$false'
        script += f"[LargePairsJoin]::RunVirtual({quote(img)},{quote(pairs)},[UInt64]::Parse('{forbidden}'),16,0,{flag})\n"
        script += f"[Residual]::RunVirtual({quote(img)},{quote(pairs)},{quote(result)},[UInt64]::Parse('{forbidden}'),{flag})\n"
        jobs.append(dict(root=name, child_deadline_fs=cut, pairs=pairs, result=result))
    run = out / 'run.ps1'
    run.write_text(script, encoding='utf-8')
    with (out / 'native.log').open('w', encoding='utf-8') as log:
        _run([pwsh, '-NoProfile', '-File', str(run)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    rows = json.loads((out / 'direct.json').read_bytes())
    for j in jobs:
        large = json.loads(Path(str(j['pairs']) + '.json').read_bytes())
        res = json.loads(j['result'].read_bytes())
        assert large['status'] == 'COMPLETE_SAFE_LARGE_AND_PAIRS'
        status = 'UNSAT' if res['status'] == 'NO_SECOND_PAIR_COMPLETES_ANY_GIVEN_COVER' else 'SAT' if res['status'] == 'SAT' else 'UNKNOWN'
        rows.append(dict(root=j['root'], status=status, child_deadline_fs=j['child_deadline_fs'], large_pairs=large, residual=res))
    report.update(status='SELECTED_ROOTS_EXCLUDED' if all((r['status'] == 'UNSAT' for r in rows)) else 'INCOMPLETE', roots=rows, seconds=time.time() - start, previous_result_files_read=0)
    save()
    print(report['status'])
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
