"""Exercise native posting-list boundaries at 63,64,65 and129 inputs."""
from ...runtime import run as _run, fail as _fail
import argparse, itertools, json, os, random, shutil, struct, subprocess, sys
from pathlib import Path
H = Path(__file__).resolve().parent
from ...model import S, M, D, maximal
from ...family_checks.library import quote

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    Y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    Z = M ^ Y
    rng = random.Random(64065)
    commands = ["$ErrorActionPreference='Stop'", 'Add-Type -Path @(' + ','.join(map(quote, [H.parent / 'PairEngine.cs', H.parent / 'oai21/OaiEngine.cs', H.parent / 'oai21/Nand3CenterProof.cs'])) + ')']
    jobs = []
    for n in (63, 64, 65, 129):
        d = out / str(n)
        d.mkdir()
        fs = []
        while len(fs) < n:
            i = len(fs)
            f = rng.getrandbits(64)
            if i % 4 == 1:
                f &= Y
            elif i % 4 == 2:
                f |= Z
            elif i % 4 == 3:
                f = M ^ fs[-1]
            if f not in fs:
                fs.append(f)
        inp = d / 'input'
        inp.write_bytes(struct.pack('<I', n) + b''.join((struct.pack('<QI', f, 22048) for f in fs)))
        known = d / 'known'
        known.write_bytes(struct.pack('<IQ', 1, 0))
        for name, klass in [('pair', 'PairEngine'), ('oai', 'OaiEngine'), ('nand3', 'Nand3CenterProof')]:
            extra = ',' + quote(known) if name == 'nand3' else ''
            commands.append(f"[{klass}]::Run({quote(inp)},{quote(d / name)},[UInt64]::Parse('{Y}'){extra})")
        jobs.append((n, d, fs))
    script = out / 'run.ps1'
    script.write_text('\n'.join(commands), encoding='utf-8')
    with (out / 'native.log').open('w') as log:
        _run([shutil.which('pwsh'), '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    results = []
    for n, d, fs in jobs:
        pair = {a & b for a, b in itertools.product(fs, repeat=2) if a & b and (not a & b & Z)}
        triple = {a & b & c for a, b, c in itertools.product(fs, repeat=3) if a & b & c and (not a & b & c & Z)}
        oai = {(a | b) & c for a, b, c in itertools.product(fs, repeat=3) if (a | b) & c and (not (a | b) & c & Z)}
        for name, expected, fmt in [('pair', pair, '<Qiii'), ('oai', set(maximal({f: 0 for f in oai})), '<Qiiii'), ('nand3', set(maximal({f: 0 for f in triple})), '<Qiiii')]:
            raw = (d / name).read_bytes()
            count, = struct.unpack_from('<I', raw)
            rows = list(struct.iter_unpack(fmt, raw[4:]))
            assert len(rows) == count
            assert {r[0] for r in rows} == expected, (n, name)
            for f, t, *ids in rows:
                v = [fs[i] for i in ids]
                truth = v[0] & v[1] if name == 'pair' else (v[0] | v[1]) & v[2] if name == 'oai' else v[0] & v[1] & v[2]
                fee = D['NAND2'] if name == 'pair' else D['OAI21'] if name == 'oai' else D['NAND3']
                assert f == truth and t == 22048 + fee
        results.append(dict(inputs=n, pair_truths=len(pair), oai_truths=len(oai), nand3_truths=len(triple)))
    report = dict(status='PASS', cases=len(results), rows=results, checks='Every posting-word boundary case compared with full Cartesian products and exact witness recomputation')
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
