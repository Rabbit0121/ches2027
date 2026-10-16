"""Audit fresh root completion AND every concrete structural-domain origin."""
from .runtime import run as _run, fail as _fail
import argparse, hashlib, json, sys, subprocess
from contextlib import nullcontext
from pathlib import Path
from .structure_catalogue import catalogue, grammar
from .model import D, PI, M
H = Path(__file__).resolve().parent
from .family_checks.certify import certify
from .family_checks.audit_library import audit

def read(p):
    return json.loads(p.read_bytes())

def verify(out):
    if not (out / 'structural_native_checks/report.json').exists():
        _run([sys.executable, str(H / 'check_structure_native.py'), '--output', str(out / 'structural_native_checks')], check=True)
    if not (out / 'structure_checks/report.json').exists():
        _run([sys.executable, str(H / 'selftest.py'), '--output', str(out / 'structure_checks/report.json')], check=True)
    if not (out / 'structural_image_crosscheck.json').exists():
        _run([sys.executable, str(H / 'check_structure_image.py'), '--image', str(out / 'quick/fresh_library/78835/image.bin'), '--output', str(out / 'structural_image_crosscheck.json')], check=True)
    structure_test = read(out / 'structure_checks/report.json')
    native_test = read(out / 'structural_native_checks/report.json')
    image_test = read(out / 'structural_image_crosscheck.json')
    assert image_test['status'] == 'PASS'
    assert structure_test['status'] == 'PASS' and structure_test['checks'] >= 185
    assert native_test['status'] == 'PASS' and native_test['gate_types'] == 21
    initial = read(out / 'source_snapshot.json')
    final_sources = {str(p.relative_to(H)): hashlib.sha256(p.read_bytes()).hexdigest() for p in H.rglob('*') if p.is_file() and p.suffix in ('.py', '.cs') and ('runs' not in p.relative_to(H).parts)}
    changed = {k: dict(before=v, after=final_sources[k]) for k, v in initial.items() if final_sources.get(k) != v}
    assert initial == final_sources, 'Proof source changed during execution'
    (out / 'final_source_snapshot.json').write_text(json.dumps(final_sources, indent=2), encoding='utf-8')
    plan = read(out / 'family_plan.json')
    assert plan['status'] == 'COMPLETE_STRUCTURAL_FAMILY_PLAN' and plan['coordinate'] == 2
    assert plan['bound_fs'] == 157297 and plan['truth_tables_evaluated'] == 0
    assert {r['root'] for r in plan['root_families']} == set(D) and len(plan['root_families']) == len(D)
    assert all((r['child_bound_fs'] == 157297 - D[r['root']] for r in plan['root_families']))
    assert hashlib.sha256((out / 'structure_grammar.json').read_bytes()).hexdigest() == plan['grammar_sha256']
    records = []
    audit_work = out / 'structure_audit_work'
    audit_work.mkdir(exist_ok=True)
    with nullcontext(audit_work) as temp:
        q = Path(temp) / 'grammar.json'
        grammar(157297, q)
        assert q.read_bytes() == (out / 'structure_grammar.json').read_bytes()
        for p in out.rglob('structure_phase.json'):
            phase = read(p)
            assert phase['status'] == 'STRUCTURE_PHASE_COMPLETE' and phase['truth_tables_evaluated'] == 0
            stages = []
            for row in phase['catalogues']:
                folder = p.parent / str(row['bound_fs'])
                q = Path(temp) / 'catalogue.json'
                regenerated = catalogue(row['bound_fs'], q)
                assert regenerated == row and q.read_bytes() == (folder / 'structures.json').read_bytes()
                c = read(folder / 'certificate.json')
                assert c['status'] == 'COMPLETE_FROM_PAID_SEEDS' and c['method'] == 'STRUCTURES_FIRST_INPUTS_SECOND'
                assert c['processed_structures'] == c['enumerated_structures'] == row['structures'] and c['previous_result_files_read'] == 0
                if (folder / 'input.bin').exists():
                    n = read(folder / 'image.bin.status.json')
                    assert n['status'] == 'COMPLETE_INPUT_EXPANSION_OF_ENUMERATED_STRUCTURES'
                    assert n['processed_structures'] == row['structures'] and n['states'] == c['functions']
                w = audit(folder)
                assert w['checked_rows'] == c['functions']
                stages.append(dict(**row, functions=c['functions'], witness_audit=w))
            records.append(dict(directory=str(p.parent.relative_to(out)), stages=stages))
    assert len(records) == 11, ('Missing or extra complete structural domain build', len(records))
    import struct
    for rec in records:
        previous = None
        for row in rec['stages']:
            folder = out / rec['directory'] / str(row['bound_fs'])
            if previous:
                with previous.open('rb') as src, (folder / 'input.bin').open('rb') as inp:
                    found, n = struct.unpack('<II', src.read(8))
                    assert not found
                    seed = [(PI[f'x{i}'] if g == 'BUF' else M ^ PI[f'x{i}'], D[g]) for i in range(6) for g in ('BUF', 'INV') if D[g] <= row['bound_fs']]
                    assert struct.unpack('<I', inp.read(4))[0] == n + len(seed)
                    for _ in range(n):
                        v, t, *_ = struct.unpack('<Qiiiiii', src.read(32))
                        assert inp.read(12) == struct.pack('<QI', v, t)
                    for v, t in seed:
                        assert inp.read(12) == struct.pack('<QI', v, t)
                    assert not src.read(1) and (not inp.read(1))
            previous = folder / 'image.bin'
    result = certify(out / 'manifest.json')
    assert result['global_lower_bound_proved'] and result['unresolved_cases'] == []
    result.update(status='PROVED_Y2_OPTIMUM_BY_STRUCTURAL_FAMILIES', coordinate=2, structure_grammar=plan, concrete_structure_domains=records, structural_checks=structure_test, native_structure_checks=native_test, per_structure_image_crosscheck=image_test, source_changes=changed, method='Complete finite structural grammar; explicit small structural catalogues followed by input expansion; exact target-only batched queries for large structure families.', literal_iteration_over_every_large_structure=False, historical_lower_bound_results_used=False)
    return result
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser()
        p.add_argument('run', type=Path)
        a = p.parse_args()
        r = verify(a.run.resolve())
        (a.run / 'final_report.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
        print(r['status'])
    except Exception as error:
        _fail(error)
