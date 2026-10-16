from ...runtime import work_reference
"""Complete NAND2 root proof: integer weights plus exhaustive exceptions.

Default execution rebuilds everything. --exception-run reuses a completed
fresh_exceptions run from this same source package, for staged reproduction.
"""
from ...runtime import run as _run, fail as _fail
import argparse, itertools, json, os, shutil, struct, subprocess, sys, time
from pathlib import Path
H = Path(__file__).resolve().parent
P = H.parent
from ...model import D, M, S, maximal
from ...family_checks.library import build, quote
from ...family_checks.oai21.centers import read_image, write_inputs, records, native
from ...family_checks.nand2.fresh_exceptions import WEIGHTS, THRESHOLD, weight, verify_dominance, read_rows
from ...family_checks.nand2.check_frontier import verify as verify_frontier
Y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
Z = M ^ Y
CUT = 157297 - D['NAND2']

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--exception-run', type=Path)
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pwsh = shutil.which('pwsh')
    assert pwsh
    start = time.time()
    report = dict(status='RUNNING', root='NAND2', root_deadline_fs=157297, child_deadline_fs=CUT, global_lower_bound_proved=False)

    def save():
        (out / 'status.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    ex = a.exception_run.resolve() if a.exception_run else out / 'exceptions'
    if not a.exception_run:
        _run([sys.executable, str(H / 'fresh_exceptions.py'), '--output', str(ex)], check=True)
    er = json.loads((ex / 'report.json').read_bytes())
    nt = json.loads((ex / 'exceptions.bin.tasks.json').read_bytes())
    nr = json.loads((ex / 'exceptions.bin.json').read_bytes())
    assert er['sublemma_status'] == 'COMPLETE_HEAVY_NAND3_COVER_ENUMERATION' and nr['status'] == 'COMPLETE'
    assert nt['start_task'] == 0 and nt['next_task'] == nt['total_tasks']
    frontier_audit = verify_frontier(ex)
    assert er['weight_total'] == sum(WEIGHTS) and er['threshold'] == THRESHOLD
    original, kept = (read_rows(ex / 'inputs.bin'), read_rows(ex / 'reduced.bin'))
    assert verify_dominance(original, kept, 94644) == er['checked_dominance_pairs']
    exceptions = []
    zero = Y & ~sum((1 << i for i, w in enumerate(WEIGHTS) if w))
    for cover, t, i, j, k in records(ex / 'exceptions.bin', '<Qiiii'):
        assert cover == kept[i][0] & kept[j][0] & kept[k][0] and (not cover & Z)
        assert t == max((kept[q][1] for q in (i, j, k))) + D['NAND3'] <= CUT and weight(cover) >= THRESHOLD
        exceptions.append(dict(cover=cover, virtual_upper_cover=cover | zero, residual=Y & ~(cover | zero)))
    assert len(exceptions) == nr['covers'] == len(er['exceptions'])
    del original, kept
    lib = out / 'library'
    lib.mkdir()
    image = build(CUT - D['NAND2'], lib, pwsh)

    def inputs(cut, mixed=False):
        rows = {f: t for f, t, *_ in read_image(image) if t <= cut}
        if mixed:
            return [(key ^ Z, t) for key, t in maximal({f ^ Z: t for f, t in rows.items()}).items()]
        return list(rows.items())
    base = out / 'nand4_leaves.bin'
    write_inputs(base, inputs(CUT - D['NAND4']))
    queries = []
    for label, weights, minimum in [('weight', WEIGHTS, THRESHOLD)] + [(f'residual_{i}', [int(e['residual'] >> b & 1) for b in range(64)], e['residual'].bit_count()) for i, e in enumerate(exceptions)]:
        assert minimum > 0
        wp = out / (label + '.weights')
        wp.write_bytes(struct.pack('<64i', *weights))
        for family in ('NAND2', 'NAND4'):
            source = image
            cut = CUT - D[family]
            product = None
            if family == 'NAND4':
                product = out / (label + '.products')
                source = product
            result = out / (label + '_' + family + '.json')
            script = out / (label + '_' + family + '.ps1')
            command = "$ErrorActionPreference='Stop'\nAdd-Type -Path " + quote(H / 'WeightedPairs.cs') + '\n'
            if product:
                command += f"[WeightedPairs]::Products({quote(base)},{quote(product)},{quote(wp)},[UInt64]::Parse('{Y}'),{cut},{minimum})\n"
            command += f"[WeightedPairs]::Run({quote(source)},{quote(result)},{quote(wp)},[UInt64]::Parse('{Z}'),{minimum},{cut},0)\n"
            script.write_text(command, encoding='utf-8')
            with (out / (label + '_' + family + '.log')).open('w') as log:
                _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
            r = json.loads(result.read_bytes())
            assert r['status'] == 'COMPLETE_NO_WEIGHT_THRESHOLD'
            assert r['minimum'] == minimum and r['cutoff'] == cut and (r['forbidden'] == Z)
            queries.append(dict(query=label, family=family, result=r))
            report.update(weighted_queries=queries)
            save()
    residual_checks = []
    for e in exceptions:
        needed = e['residual']
        common = M
        n = 0
        for f, t, *_ in read_image(image):
            if t <= CUT - D['NAND3'] and f & needed == needed:
                common &= f
                n += 1
        assert n == 0 or common & Z, 'No common forbidden bit: use general residual cover search'
        residual_checks.append(dict(residual=needed, eligible_inputs=n, common_forbidden=common & Z))
    covers = {}

    def add(c, t):
        assert not c & Z and t <= CUT
        covers[c] = min(t, covers.get(c, t))
    for f, t, *_ in read_image(image):
        if f & Z == Z:
            add(M ^ f, t)
    invcut = CUT - D['INV']
    il = out / 'inv_library'
    il.mkdir()
    ii = build(invcut - min(D.values()), il, pwsh)
    ip = out / 'inv_inputs.bin'
    write_inputs(ip, [(f, t) for f, t, *_ in read_image(ii)])
    invout = out / 'inv_image.bin'
    native(out, 'inv', P / 'root_cases/CSubsetImage.cs', [quote(ip), quote(invout), str(invcut), f"[UInt64]::Parse('{Z}')"], pwsh)
    for f, t, *_ in read_image(invout):
        add(f, t + D['INV'])
    for gate in ('OAI22', 'AOI22'):
        rows = inputs(CUT - D[gate], True)
        if gate == 'OAI22':
            pairs = {}
            for (a, ta), (b, tb) in itertools.combinations_with_replacement(rows, 2):
                key = (a | b) ^ Z
                t = max(ta, tb)
                pairs[key] = min(t, pairs.get(key, t))
            rows = [(key ^ Z, t) for key, t in maximal(pairs).items()]
        inp, res = (out / (gate + '.input'), out / (gate + '.result'))
        write_inputs(inp, rows)
        native(out, gate, P / 'PairEngine.cs', [quote(inp), quote(res), f"[UInt64]::Parse('{Y}')"], pwsh)
        products = {}
        for c, _, i, j in records(res, '<Qiii'):
            t = max(rows[i][1], rows[j][1])
            assert c == rows[i][0] & rows[j][0]
            if gate == 'AOI22':
                products[c] = min(t, products.get(c, t))
            else:
                add(c, t + D[gate])
        if gate == 'AOI22':
            for (a, ta), (b, tb) in itertools.combinations_with_replacement(list(maximal(products).items()), 2):
                add(a | b, max(ta, tb) + D[gate])
    inp, res = (out / 'OAI21.input', out / 'OAI21.result')
    rows = inputs(CUT - D['OAI21'], True)
    write_inputs(inp, rows)
    native(out, 'OAI21', P / 'oai21/OaiEngine.cs', [quote(inp), quote(res), f"[UInt64]::Parse('{Y}')"], pwsh)
    for c, t, i, j, k in records(res, '<Qiiii'):
        assert c == (rows[i][0] | rows[j][0]) & rows[k][0]
        add(c, t)
    inp, res = (out / 'remaining.input', out / 'remaining.result')
    write_inputs(inp, inputs(CUT - D['AND2']))
    native(out, 'remaining', P / 'oai21/RemainingImage.cs', [quote(inp), quote(res), str(CUT), f"[UInt64]::Parse('{Z}')"], pwsh)
    for f, t, *_ in read_image(res):
        add(M ^ f, t)
    covers = maximal(covers)
    maxw = max(map(weight, covers), default=0)
    assert maxw < THRESHOLD
    for e in exceptions:
        assert all((e['residual'] & ~c for c in covers))
    (out / 'auxiliary_covers.json').write_text(json.dumps(dict(covers=list(covers), max_weight=maxw)), encoding='utf-8')
    report.update(status='ROOT_EXCLUDED', root_result='UNSAT', weighted_queries=queries, exceptions=exceptions, nand3_residual_checks=residual_checks, other_families_max_weight=maxw, other_families_cover_count=len(covers), weight_total=sum(WEIGHTS), threshold=THRESHOLD, exception_source=work_reference(ex), frontier_audit=frontier_audit, seconds=time.time() - start)
    save()
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
