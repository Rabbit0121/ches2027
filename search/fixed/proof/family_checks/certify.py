from ..runtime import work_path, work_reference
"""Aggregate only completed root proofs and recompute the upper-bound witness.

This is an executable completion audit, not a substitute for the completeness
the structural coverage rules or for the exhaustive native kernels it audits.
"""
from ..runtime import run as _run, fail as _fail
import argparse, json, struct, sys, time
from pathlib import Path
from ..model import D, S, M, audit, expression
from ..family_checks.normal_forms import check as normal_forms
from ..family_checks.root_cases.cover_certificate import verify
from ..family_checks.nand2.fresh_exceptions import WEIGHTS, THRESHOLD, weight
from ..family_checks.nand2.check_frontier import verify as verify_frontier

def read(p):
    return json.loads(p.read_bytes())

def certify(manifest_path):
    manifest = read(manifest_path)
    base = manifest_path.parent
    paths = {k: (base / v).resolve() for k, v in manifest.items()}
    Y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    Z = M ^ Y
    for name in ('native_checks', 'kernel_checks'):
        r = read(paths[name] / 'report.json')
        assert r['status'] == 'PASS' and r['cases'] >= 32
    r = read(paths['word_checks'] / 'report.json')
    assert r['status'] == 'PASS' and {q['inputs'] for q in r['rows']} == {63, 64, 65, 129}
    roots = {}
    tails = {}
    finite = []

    def accept(name, evidence, method):
        fee = sum((D[g] for g in name.split('_')))
        record = dict(root=name, status='EXCLUDED', tail_cost_fs=fee, input_deadline_fs=157297 - fee, method=method, evidence=work_reference(evidence))
        if name.startswith('INV_'):
            tails[name] = record
        else:
            assert name in D
            roots[name] = record
    for name, expected in [('quick', {'XOR2', 'XNOR2', 'OR2', 'NOR3', 'NOR4', 'OR3', 'OR4', 'AND4', 'MUX2', 'NAND4'}), ('more', {'INV_NOR3', 'INV_NOR4', 'INV_MUX2', 'INV_AOI21', 'INV_OAI21', 'AOI22', 'OAI22', 'INV_AOI22', 'INV_OAI22'})]:
        p = paths[name] / 'status.json'
        r = read(p)
        assert r['status'] == 'SELECTED_ROOTS_EXCLUDED' and r['root_deadline_fs'] == 157297
        assert {q['root'] for q in r['roots']} == expected
        for q in r['roots']:
            assert q['status'] == 'UNSAT'
            accept(q['root'], p, 'Complete common-deadline root-specific query')
    finite.append(verify(paths['quick'] / 'nand4_certificate'))
    for name in ('aoi21', 'nand3', 'nor2', 'and2', 'and3'):
        p = paths[name] / 'status.json'
        r = read(p)
        root = r['root']
        assert root == name.upper() and r['status'] == 'ROOT_EXCLUDED' and (r['root_result'] == 'UNSAT')
        assert r['root_deadline_fs'] == 157297 and r['child_deadline_fs'] == 157297 - D[root]
        accept(root, p, 'Complete child basis plus exact finite query')
        if root != 'AOI21':
            finite.append(verify(paths[name] / 'cover_certificate'))
        else:
            native = read(paths[name] / 'stream.json')
            assert native['status'] == 'COMPLETE_NO_AOI21_AT_BOUND' and native['bound'] == 157297 - D[root]
    p = paths['nand2'] / 'status.json'
    r = read(p)
    assert r['status'] == 'ROOT_EXCLUDED' and r['root_result'] == 'UNSAT' and (r['child_deadline_fs'] == 129411)
    assert r['weight_total'] == sum(WEIGHTS) == 115697 and r['threshold'] == THRESHOLD == 57849
    assert 2 * (THRESHOLD - 1) < sum(WEIGHTS)
    queries = {(q['query'], q['family']): q['result'] for q in r['weighted_queries']}
    for key, v in queries.items():
        assert v['status'] == 'COMPLETE_NO_WEIGHT_THRESHOLD' and v['forbidden'] == Z
    for family in ('NAND2', 'NAND4'):
        v = queries['weight', family]
        assert v['minimum'] == THRESHOLD and v['cutoff'] == 129411 - D[family]
    aux = read(paths['nand2'] / 'auxiliary_covers.json')
    assert all((c & Z == 0 for c in aux['covers']))
    assert max(map(weight, aux['covers'])) == r['other_families_max_weight'] < THRESHOLD
    exception_path = work_path(r['exception_source'])
    ex = read(exception_path / 'report.json')
    tasks = read(exception_path / 'exceptions.bin.tasks.json')
    native = read(exception_path / 'exceptions.bin.json')
    assert ex['sublemma_status'] == 'COMPLETE_HEAVY_NAND3_COVER_ENUMERATION' and native['status'] == 'COMPLETE'
    assert tasks['start_task'] == 0 and tasks['next_task'] == tasks['total_tasks'] == ex['completed_tasks']
    assert len(r['exceptions']) == native['covers']
    frontier_audit = verify_frontier(exception_path)
    for i, e in enumerate(r['exceptions']):
        need = e['residual']
        assert need == Y & ~e['virtual_upper_cover']
        assert all((need & ~c for c in aux['covers']))
        for family in ('NAND2', 'NAND4'):
            q = queries[f'residual_{i}', family]
            assert q['minimum'] == need.bit_count() and q['cutoff'] == 129411 - D[family]
        q = r['nand3_residual_checks'][i]
        assert q['residual'] == need and (q['eligible_inputs'] == 0 or q['common_forbidden'] & Z)
    accept('NAND2', p, 'Nonnegative integer weights; exhaustive heavy exceptions; every exceptional residual excluded')
    p = paths['oai21_final'] / 'status.json'
    r = read(p)
    assert r['status'] == 'ROOT_EXCLUDED' and r['root_result'] == 'UNSAT' and (r['child_deadline_fs'] == 124646)
    needed = {'INV', 'NAND2', 'AND2', 'NOR2', 'NAND3', 'NAND4', 'OAI21', 'cheap11', 'aoi3', 'OAI21_P_identity', 'OAI21_W_identity'}
    assert set(r['completed_families']) == needed
    constant_expression = ['NAND2', ['BUF', 'x0'], ['INV', 'x0']]
    constant_truth, constant_time = expression(constant_expression)
    assert constant_truth == M and constant_time <= 124646 - D['OAI21']
    q = read(paths['oai21_final'] / 'final_query.json')
    assert q == r['final_query']
    assert q['status'] == 'COMPLETE_NO_COMMON_CENTER_TWO_COVER' and q['Y'] == Y and (q['Z'] == Z)
    merged = paths['oai21_final'] / 'all_inner.truths'
    with merged.open('rb') as f:
        n, = struct.unpack('<I', f.read(4))
    assert n == q['input_records'] and merged.stat().st_size == 4 + 8 * n
    block_names = ['INV_final', 'NAND2_final', 'AND2_final', 'NOR2_final', 'NAND3_final', 'NAND4_final', 'OAI21_products', 'OAI21_W', 'OAI21_final', 'cheap11_final', 'aoi3_final']
    block_rows = 0
    with merged.open('rb') as whole:
        whole.read(4)
        for name in block_names:
            with (paths['oai21_final'] / (name + '.max.truths')).open('rb') as part:
                count, = struct.unpack('<I', part.read(4))
                block_rows += count
                assert part.seek(0, 2) == 4 + 8 * count
                part.seek(4)
                while (chunk := part.read(1024 * 1024)):
                    assert whole.read(len(chunk)) == chunk
        assert not whole.read(1)
    assert block_rows == n
    center_source = read(work_path(r['center_source']) / 'centers.json')
    with (paths['oai21_final'] / 'centers.bin').open('rb') as f:
        count, = struct.unpack('<I', f.read(4))
        centers = [struct.unpack('<Q', f.read(8))[0] for _ in range(count)]
        assert not f.read(1)
    assert centers == center_source['zero_covers'] and count == q['centers'] == r['center_count']
    assert q['downset'] == r['downset_count']
    maps = []
    for f in paths['oai21_final'].glob('*.max.json'):
        m = read(f)
        assert m['status'] == 'COMPLETE_EXACT_MIXED_MAXIMA'
        name = f.name[:-len('.max.json')]
        v = read(paths['oai21_final'] / (name + '.audit') / 'native.json')
        assert v['status'] == 'ALL_SOURCE_ROWS_HAVE_EXPLICIT_DOMINATOR' and v['rows'] == m['source_rows']
        assert v['maxima'] == m['maximal_functions'] and m['xor_mask'] == Y
        witness = paths['oai21_final'] / (name + '.audit') / 'source0.witness.bin'
        with witness.open('rb') as w:
            rows, = struct.unpack('<I', w.read(4))
        assert rows == v['rows'] and witness.stat().st_size == 4 + 4 * rows
        maps.append(dict(name=name, source_rows=m['source_rows'], representatives=m['maximal_functions']))
    expected_maps = set(block_names) | {'NAND2_leaves', 'AND2_leaves', 'NOR2_leaves', 'NAND3_leaves', 'NAND4_leaves', 'NAND4_symbolic', 'OAI21_all_leaves'}
    assert {m['name'] for m in maps} == expected_maps
    accept('OAI21', p, 'Complete centers, all 21 inner gate families, explicit dominance maps, exact common-center pair exclusion')
    nf = normal_forms()
    assert nf['seed_excluded'] and set(tails) == set(nf['required_irreducible_tail_exclusions'])
    accept('INV', paths['more'] / 'status.json', 'Checked terminal-inverter reductions and all seven irreducible tails')
    accept('BUF', paths['more'] / 'status.json', 'Remove terminal identity BUF from a minimum-delay nonliteral realization')
    assert set(roots) == set(D) and len(roots) == 21
    upper = read(paths['upper'] / 'y2_upper_witness.json')
    truth, arrival = expression(upper['expression'])
    assert truth == Y and arrival == 157298 and (upper['coordinate'] == 2)
    upper = dict(coordinate=2, truth=truth, arrival_fs=arrival, boundary_BUF_INV=True)
    return dict(status='PROVED_Y2_THEORETICAL_OPTIMUM', optimal_delay_fs=157298, excluded_deadline_fs=157297, target_y2=Y, model='Fixed model.py S0 and all 21 integer-fs gate costs; paid BUF/INV input boundary; no free external constants; repeated pins allowed; unbounded finite DAG area and fanout', proof_kind='Computer-assisted exhaustive proof; trusted reviewed native enumerators plus Python cross-checks; not a Lean/Coq formal proof', upper_bound=upper, root_cases=[roots[g] for g in D], terminal_inv_tails=list(tails.values()), normal_form_checks=nf, independently_verified_finite_covers=finite, nand2_frontier_audit=frontier_audit, oai21_dominance_maps=maps, oai21_identity_constant=dict(expression=constant_expression, arrival_fs=constant_time), unresolved_cases=[], global_lower_bound_proved=True)
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument('--manifest', required=True, type=Path)
        p.add_argument('--output', required=True, type=Path)
        a = p.parse_args()
        start = time.time()
        result = certify(a.manifest.resolve())
        result['audit_seconds'] = time.time() - start
        a.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(result['status'])
    except Exception as error:
        _fail(error)
