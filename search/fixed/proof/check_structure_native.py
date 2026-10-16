"""Exhaustive input oracle for all 21 gate types and all paid leaf phases."""
from .runtime import run as _run, fail as _fail
import argparse, itertools, json, os, shutil, struct, subprocess, time
from pathlib import Path
from .model import D, ARITY, PI, M, gate
from .build_structured_library import quote
H = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    start = time.time()
    names = list(D)
    seed = [(f if g == 'BUF' else M ^ f, D[g]) for g in ('INV', 'BUF') for f in PI.values()]
    inp = out / 'input.bin'
    inp.write_bytes(struct.pack('<I', len(seed)) + b''.join((struct.pack('<QI', f, t) for f, t in seed)))
    nodes = [dict(gate=names.index(g), children=[], delay=D[g]) for g in ('INV', 'BUF')]
    expected = dict(seed)
    tuples = 0
    for g in D:
        for phases in itertools.product((0, 1), repeat=ARITY[g]):
            t = max((D['INV' if p == 0 else 'BUF'] for p in phases)) + D[g]
            nodes.append(dict(gate=names.index(g), children=list(phases), delay=t))
            for labels in itertools.product(range(6), repeat=ARITY[g]):
                terms = [seed[p * 6 + i][0] for p, i in zip(phases, labels)]
                f = gate(g, terms)
                expected[f] = min(t, expected.get(f, t))
                tuples += 1
    bound = max((q['delay'] for q in nodes))
    cat = out / 'structures.json'
    cat.write_text(json.dumps(dict(bound_fs=bound, structures=len(nodes), truth_tables_evaluated=0, nodes=nodes)), encoding='utf-8')
    dest = out / 'image.bin'
    script = out / 'run.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n" + f"Add-Type -Path {quote(H / 'StructureImage.cs')}\n[StructureImage]::Run({quote(inp)},{quote(cat)},{quote(dest)},{bound},33557)\n", encoding='utf-8')
    with (out / 'native.log').open('w') as log:
        _run([shutil.which('pwsh'), '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    with dest.open('rb') as f:
        found, n = struct.unpack('<II', f.read(8))
        assert not found
        got = {v: t for v, t, *_ in struct.iter_unpack('<Qiiiiii', f.read())}
    assert len(got) == n and got == expected
    r = dict(status='PASS', gate_types=len(D), structures=len(nodes), ordered_input_assignments=tuples, functions=n, comparison='Every truth table and minimum arrival across all paid phases, full ordered Python assignments versus native expansion', seconds=time.time() - start)
    (out / 'report.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    print(json.dumps(r))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
