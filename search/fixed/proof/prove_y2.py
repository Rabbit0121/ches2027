"""Complete Y2 proof: structural grammar/catalogues, then exact input queries.

Large products are processed as finite structure families. This is not literal
iteration over 10^20 shapes, and no historical lower-bound result is consumed.
"""
from .runtime import run as _run, fail as _fail
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from .structure_catalogue import grammar
from .model import D
H = Path(__file__).resolve().parent
K = H / 'family_checks'
JOBS = [('native_checks', 'check_native.py', []), ('kernel_checks', 'root_cases/check_kernels.py', []), ('word_checks', 'root_cases/check_word_boundaries.py', []), ('quick', 'root_cases/quick_roots.py', ['--nand4']), ('more', 'root_cases/more_roots.py', []), ('aoi21', 'root_cases/filtered_roots.py', ['--root', 'AOI21']), ('nand3', 'oai21/centers.py', ['--root', 'NAND3']), ('nor2', 'root_cases/filtered_roots.py', ['--root', 'NOR2']), ('and2', 'oai21/centers.py', ['--root', 'AND2']), ('and3', 'oai21/centers.py', ['--root', 'AND3']), ('nand2', 'nand2/complete.py', []), ('oai21_final', 'oai21/complete.py', [])]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    progress = out / 'progress.json'
    if a.resume:
        r = json.loads(progress.read_bytes())
        done = r['completed']
        start = time.monotonic() - r['elapsed_seconds']
    else:
        out.mkdir(parents=True, exist_ok=False)
        done = []
        start = time.monotonic()
        g = grammar(157297, out / 'structure_grammar.json')
        binding = {root: job for job, roots in [('quick', ['XOR2', 'XNOR2', 'OR2', 'NOR3', 'NOR4', 'OR3', 'OR4', 'AND4', 'MUX2', 'NAND4']), ('more', ['AOI22', 'OAI22', 'INV']), ('aoi21', ['AOI21']), ('nand3', ['NAND3']), ('nor2', ['NOR2']), ('and2', ['AND2']), ('and3', ['AND3']), ('nand2', ['NAND2']), ('oai21_final', ['OAI21']), ('normal_form', ['BUF'])] for root in roots}
        assert set(binding) == set(D)
        plan = dict(status='COMPLETE_STRUCTURAL_FAMILY_PLAN', coordinate=2, bound_fs=157297, structure_count=g['structure_count'], grammar_sha256=hashlib.sha256((out / 'structure_grammar.json').read_bytes()).hexdigest(), root_families=[dict(root=root, child_bound_fs=157297 - D[root], checker=binding[root]) for root in D], semantics='Each child hole denotes all timing-feasible paid-boundary structures. Independent holes may choose the same structure and different input assignments. Root gate pin symmetries are exact. Family image is the union of all constituent structure images.', input_stage='Concrete catalogues are generated before input expansion. Exact target joins may batch unions of structure images; checked dominance may reduce only the query domain, preserving existence.', truth_tables_evaluated=0)
        (out / 'family_plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        (out / 'upper').mkdir()
        shutil.copyfile(H / 'y2_upper_witness.json', out / 'upper/y2_upper_witness.json')
        sources = {str(p.relative_to(H)): hashlib.sha256(p.read_bytes()).hexdigest() for p in H.rglob('*') if p.is_file() and p.suffix in ('.py', '.cs') and ('runs' not in p.relative_to(H).parts)}
        (out / 'source_snapshot.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')

    def save(status, current=None, **extra):
        progress.write_text(json.dumps(dict(status=status, current=current, completed=done, elapsed_seconds=time.monotonic() - start, global_lower_bound_proved=False, **extra), indent=2), encoding='utf-8')
    for name, source, args in JOBS:
        if name in done:
            continue
        save('RUNNING', name)
        print('Running ' + name, flush=True)
        try:
            with (out / (name + '.log')).open('w', encoding='utf-8') as log:
                _run([sys.executable, str(K / source), *args, '--output', str(out / name)], check=True, stdout=log, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            save('FAILED', name, returncode=e.returncode)
            raise
        done.append(name)
        save('RUNNING')
        print('Completed ' + name, flush=True)
    manifest = {name: name for name, _, _ in JOBS}
    manifest['upper'] = 'upper'
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save('AUDITING_STRUCTURAL_COVERAGE')
    from .verify_y2 import verify
    r = verify(out)
    r['total_seconds'] = time.monotonic() - start
    (out / 'final_report.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    progress.write_text(json.dumps(dict(status=r['status'], completed=done, elapsed_seconds=time.monotonic() - start, global_lower_bound_proved=True), indent=2), encoding='utf-8')
    print(r['status'])
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
