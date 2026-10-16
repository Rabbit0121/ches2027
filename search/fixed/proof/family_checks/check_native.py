from ..runtime import work_relative
"""Independent exhaustive Python oracles for all specialized native proof kernels."""
from ..runtime import run as _run, fail as _fail
import argparse, itertools, json, os, random, shutil, struct, subprocess, sys
from pathlib import Path
from ..model import M, D, ARITY, gate, maximal
from ..family_checks.library import quote
H = Path(__file__).resolve().parent

def save_image(p, fs, ts):
    with p.open('wb') as f:
        f.write(struct.pack('<II', 0, len(fs)))
        for v, t in zip(fs, ts):
            f.write(struct.pack('<Qiiiiii', v, t, -1, -1, -1, -1, -1))

def save_inputs(p, fs, ts):
    p.write_bytes(struct.pack('<I', len(fs)) + b''.join((struct.pack('<QI', v, t) for v, t in zip(fs, ts))))

def data(p, fmt, header=4):
    raw = p.read_bytes()
    n, = struct.unpack_from('<I', raw, header - 4)
    size = struct.calcsize(fmt)
    assert len(raw) == header + n * size
    return list(struct.iter_unpack(fmt, raw[header:]))

def dominates(actual, expected, flip):
    assert all((any(((a ^ flip) & (e ^ flip) == e ^ flip for a in actual)) for e in expected))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(157298)
    jobs = []
    commands = ["$ErrorActionPreference='Stop'"]
    sources = [H / 'FullImage.cs', H / 'PairEngine.cs', H / 'nand2/WeightedPairs.cs', H / 'nand2/WeightedInputMax.cs', H / 'nand2/PartitionedWeightedTripleJoin.cs', H / 'root_cases/CSubsetImage.cs'] + [H / 'oai21' / (s + '.cs') for s in ['GlobalPairs', 'GlobalCross', 'GlobalTriple', 'OaiFinalCover', 'MixedMaxFast', 'GlobalCheapFull', 'GlobalAoiFull', 'Nand3CenterProof', 'OaiEngine', 'RemainingImage']]
    commands.append('Add-Type -Path @(' + ','.join(map(quote, sources)) + ')')
    for case in range(32):
        d = out / str(case)
        d.mkdir()
        n = case % 8
        Y = 15
        Z = M ^ Y
        fs = list(dict.fromkeys((rng.randrange(256) | (M ^ 255 if rng.randrange(2) else 0) for _ in range(n))))
        n = len(fs)
        cost = [1, 22048, 60000][case % 3]
        ts = [cost] * n
        cs = list(dict.fromkeys([rng.randrange(16) for _ in range(1 + case % 4)]))
        allowed = {q for c in cs for q in range(16) if q & ~c == 0}
        center = d / 'centers'
        center.write_bytes(struct.pack('<I', len(cs)) + b''.join((struct.pack('<Q', c) for c in cs)))
        inp = d / 'input'
        img = d / 'image'
        save_inputs(inp, fs, ts)
        save_image(img, fs, ts)
        jobs.append(dict(d=d, fs=fs, ts=ts, Y=Y, cs=cs, allowed=allowed, cost=cost))
        u = lambda x: f"[UInt64]::Parse('{x}')"
        for name, flag in [('and', '$false'), ('or', '$true')]:
            commands.append(f'[GlobalPairs]::Run({quote(center)},{quote(img)},{quote(d / name)},{u(Y)},{flag},$true)')
        cross = d / 'cross_input'
        with cross.open('wb') as f:
            f.write(struct.pack('<II', 0, n))
            for i, (v, t) in enumerate(zip(fs, ts)):
                f.write(struct.pack('<Qiiiiii', v, t, -2 if i % 2 else -1, -1, -1, -1, -1))
        commands.append(f"[GlobalCross]::Run({quote(center)},{quote(cross)},{quote(d / 'cross')},{u(Y)},$true,$true)")
        commands.append(f"[GlobalTriple]::Run({quote(center)},{quote(inp)},{quote(d / 'triple')},{u(Y)})")
        compat = [v for v in fs if v & Y in allowed]
        fp = d / 'final_input'
        fp.write_bytes(struct.pack('<I', len(compat)) + b''.join((struct.pack('<Q', v) for v in compat)))
        commands.append(f"[OaiFinalCover]::Run({quote(center)},{quote(fp)},{quote(d / 'final.json')},{u(Y)},0)")
        manifest = d / 'manifest'
        manifest.write_text(f'0\t{work_relative(img)}\t8\t32\t4\n', encoding='utf-8')
        commands.append(f"[MixedMaxFast]::Run({quote(manifest)},'',{quote(d / 'max')},{u(Y)})")
        for engine in ['GlobalCheapFull', 'GlobalAoiFull']:
            commands.append(f'[{engine}]::Run({quote(inp)},{quote(d / engine)},124646,{u(Y)},{quote(center)})')
        commands.append(f"[CSubsetImage]::Run({quote(inp)},{quote(d / 'subset')},124646,{u(Y)})")
        commands.append(f"[RemainingImage]::Run({quote(inp)},{quote(d / 'remaining')},124646,{u(Y)})")
        commands.append(f"[PairEngine]::Run({quote(inp)},{quote(d / 'pair')},{u(Y)})")
        commands.append(f"[OaiEngine]::Run({quote(inp)},{quote(d / 'oai')},{u(Y)})")
        known = d / 'known'
        known.write_bytes(struct.pack('<IQ', 1, 0))
        commands.append(f"[Nand3CenterProof]::Run({quote(inp)},{quote(d / 'nand3')},{u(Y)},{quote(known)})")
        weights = [rng.randrange(5) if Y >> b & 1 else 0 for b in range(64)]
        threshold = max(1, sum(weights) // 2)
        wp = d / 'weights'
        wp.write_bytes(struct.pack('<64i', *weights))
        commands.append(f"[WeightedPairs]::Run({quote(img)},{quote(d / 'weighted.json')},{quote(wp)},{u(M ^ Y)},{threshold},60000,0)")
        commands.append(f"[WeightedPairs]::Products({quote(inp)},{quote(d / 'products')},{quote(wp)},{u(Y)},60000,{threshold})")
        commands.append(f"[WeightedInputMax]::Run({quote(inp)},{quote(wp)},{quote(d / 'weighted_reduced')},{u(Y)},{threshold})")
        commands.extend([f'$env:NAND3_WEIGHTS_PATH={quote(wp)}', "$env:NAND3_STOP_FIRST='0'", "$env:NAND3_START_TASK='0'", f"$env:NAND3_FRONTIER_SIZE='{1 + case % 7}'"])
        for method in ['Run', 'RunGood']:
            commands.append(f"[PartitionedWeightedTripleJoin]::{method}({quote(d / 'weighted_reduced')},{quote(d / ('weighted_triples_' + method))},{u(Y)},{threshold},0)")
        jobs[-1].update(weights=weights, threshold=threshold)
    ps = out / 'run.ps1'
    ps.write_text('\n'.join(commands) + '\n', encoding='utf-8')
    with (out / 'native.log').open('w') as log:
        _run([shutil.which('pwsh'), '-NoProfile', '-File', str(ps)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    stats = {}
    sat = 0
    for j in jobs:
        d, fs, ts, Y, allowed = (j[k] for k in ('d', 'fs', 'ts', 'Y', 'allowed'))
        Z = M ^ Y
        cost = j['cost']
        for name, op in [('and', lambda a, b: a & b), ('or', lambda a, b: a | b)]:
            expected = {op(a, b) for a, b in itertools.product(fs, repeat=2) if op(a, b) & Y in allowed and op(a, b) & Z}
            actual = {r[0] for r in data(d / name, '<Qiii')}
            assert actual <= expected
            dominates(actual, expected, Y)
        expected = {a | b | c for a, b, c in itertools.product(fs, repeat=3) if (a | b | c) & Y in allowed and (a | b | c) & Z}
        assert {r[0] for r in data(d / 'triple', '<Q')} == expected
        expected = {a | b for i, a in enumerate(fs) for k, b in enumerate(fs) if i % 2 != k % 2 and a & Z and b & Z and ((a | b) & Y in allowed)}
        assert {r[0] for r in data(d / 'cross', '<Qiii')} == expected
        expected = any(((a | b) & Z == Z and (a | b) & Y in allowed for a, b in itertools.product(fs, repeat=2)))
        actual = json.loads((d / 'final.json').read_bytes())
        assert (actual['status'] == 'SAT_COMMON_CENTER_TWO_COVER') == expected
        sat += expected
        actual = {r[0] for r in data(Path(str(d / 'max') + '.truths'), '<Q')}
        expected = {k ^ Y for k in maximal({v ^ Y: 0 for v in fs})}
        assert actual == expected
        for name, names, compatible, flip in [('GlobalCheapFull', ['BUF', 'OR2', 'XOR2', 'XNOR2', 'NOR3', 'AND3', 'OR3', 'MUX2', 'NOR4', 'AND4', 'OR4'], lambda f: f & Y in allowed, Y), ('GlobalAoiFull', ['AOI21', 'OAI22', 'AOI22'], lambda f: f & Y in allowed, Y), ('subset', list(D), lambda f: f & Y == 0, Y), ('remaining', [g for g in D if g not in ('INV', 'BUF', 'NAND2', 'NAND3', 'NAND4', 'OAI21', 'OAI22', 'AOI22')], lambda f: f & Y == Y, M ^ Y)]:
            expected = {f: cost for f in fs if compatible(f)}
            for g in names:
                if cost + D[g] > 124646:
                    continue
                for args in itertools.product(fs, repeat=ARITY[g]):
                    v = gate(g, args)
                    if compatible(v):
                        expected[v] = min(expected.get(v, 10 ** 9), cost + D[g])
            rows = data(d / name, '<Qiiiiii', 8)
            actual = {r[0] for r in rows}
            assert actual <= expected.keys(), name
            dominates(actual, expected.keys(), flip)
            if name != 'GlobalAoiFull':
                assert actual == expected.keys(), name
            for r in rows:
                v, t, g, *ids = r
                if g == -1:
                    assert v == fs[ids[0]] and t == ts[ids[0]]
                else:
                    typ = list(D)[g]
                    args = [fs[i] for i in ids[:ARITY[typ]]]
                    assert gate(typ, args) == v and t == cost + D[typ]
        expected = {a & b for a, b in itertools.product(fs, repeat=2) if a & b & Z == 0 and a & b}
        assert {r[0] for r in data(d / 'pair', '<Qiii')} == expected
        expected = {(a | b) & c for a, b, c in itertools.product(fs, repeat=3) if (a | b) & c & Z == 0}
        actual = {r[0] for r in data(d / 'oai', '<Qiiii')}
        assert actual <= expected
        dominates(actual | {0}, expected, 0)
        expected = {a & b & c for a, b, c in itertools.product(fs, repeat=3) if a & b & c & Z == 0}
        actual = {r[0] for r in data(d / 'nand3', '<Qiiii')}
        assert actual <= expected
        dominates(actual | {0}, expected, 0)
        w = lambda f: sum((v for b, v in enumerate(j['weights']) if f >> b & 1))
        expected = any((a & b & Z == 0 and w(a & b) >= j['threshold'] for a, b in itertools.product(fs, repeat=2)))
        result = json.loads((d / 'weighted.json').read_bytes())
        assert (result['status'] == 'SAT_WEIGHT_THRESHOLD') == expected
        expected = {a & b for a, b in itertools.product(fs, repeat=2) if w(a & b) >= j['threshold']}
        assert {r[0] for r in data(d / 'products', '<Qiiiiii', 8)} == expected
        kept = data(d / 'weighted_reduced', '<QI')
        positive = sum((1 << b for b, v in enumerate(j['weights']) if v))
        for f, t in kept:
            assert f in fs and t == cost
        for f in fs:
            if w(f) >= j['threshold']:
                assert any((not f & positive & ~g and (not g & Z & ~f) for g, t in kept))
        expected = {a & b & c for (a, _), (b, _), (c, _) in itertools.product(kept, repeat=3) if a & b & c & Z == 0 and w(a & b & c) >= j['threshold']}
        for method in ['Run', 'RunGood']:
            path = d / ('weighted_triples_' + method)
            rows = data(path, '<Qiiii')
            assert {r[0] for r in rows} == expected
            for f, t, i, k, l in rows:
                assert f == kept[i][0] & kept[k][0] & kept[l][0] and t == cost + D['NAND3']
            status = json.loads(Path(str(path) + '.json').read_bytes())
            tasks = json.loads(Path(str(path) + '.tasks.json').read_bytes())
            assert status['status'] == 'COMPLETE' and tasks['start_task'] == 0 and (tasks['next_task'] == tasks['total_tasks'])
    report = dict(status='PASS', cases=len(jobs), final_cover_sat_cases=sat, checks='Complete Cartesian product comparisons, real membership and dominance, zero/empty domains, repeated pins, exact witness truth and timing, weighted thresholds and symbolic products', kernels=[p.stem for p in sources])
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
