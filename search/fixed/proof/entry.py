"""Plan, check, run, and audit the fixed APN6 lower-bound computation."""
import json
from pathlib import Path
from .model import D, S, expression
from .count_shapes import INV_TAILS
from .structure_catalogue import grammar
from .family_checks.normal_forms import check as normal_forms
from .runtime import ROOT, configure, run

BOUND = 157297
UPPER = 157298


def root_plan():
    groups = {
        'quick': ('XOR2', 'XNOR2', 'OR2', 'NOR3', 'NOR4', 'OR3', 'OR4', 'AND4', 'MUX2', 'NAND4'),
        'more': ('AOI22', 'OAI22'), 'aoi21': ('AOI21',), 'nand3': ('NAND3',),
        'nor2': ('NOR2',), 'and2': ('AND2',), 'and3': ('AND3',),
        'nand2': ('NAND2',), 'oai21_final': ('OAI21',)}
    cases = [dict(root=gate, child_deadline_fs=BOUND-D[gate], stage=stage)
             for stage, gates in groups.items() for gate in gates]
    cases += [dict(root='INV_'+gate, child_deadline_fs=BOUND-D['INV']-D[gate], stage='more')
              for gate in INV_TAILS]
    assert len(cases) == 26 and len({c['root'] for c in cases}) == 26
    assert {c['root'] for c in cases if not c['root'].startswith('INV_')} == set(D)-{'BUF','INV'}
    return cases


def execute(stage, output, resume=False):
    output = Path(output).resolve()
    configure(output)
    if stage == 'run':
        import sys
        args = [sys.executable, str(ROOT/'prove_y2.py'), '--output', str(output)]
        if resume:
            args.append('--resume')
        run(args, check=True)
        return json.loads((output/'final_report.json').read_text())
    if stage == 'audit':
        import sys
        run([sys.executable, str(ROOT/'verify_y2.py'), str(output)], check=True)
        return json.loads((output/'final_report.json').read_text())
    if resume:
        raise ValueError('Resume applies to a complete proof run')
    output.mkdir(parents=True, exist_ok=False)
    if stage == 'check':
        import sys
        run([sys.executable, str(ROOT/'selftest.py'), '--output', str(output/'selftest.json')], check=True)
        witness = json.loads((ROOT/'y2_upper_witness.json').read_text())
        truth, arrival = expression(witness['expression'])
        assert witness['coordinate']==2 and arrival==UPPER
        assert truth==sum(((v>>2)&1)<<x for x,v in enumerate(S))
        report = dict(status='LOCAL_CHECKS_PASSED', upper_bound_fs=arrival,
                      checks=json.loads((output/'selftest.json').read_text()),
                      normal_forms=normal_forms(), root_cases=root_plan(), global_lower_bound_proved=False)
    elif stage == 'plan':
        g = grammar(BOUND, output/'structure_grammar.json')
        report = dict(status='STRUCTURAL_PLAN_COMPLETE', coordinate=2,
                      bound_fs=BOUND, grammar_states=len(g['states']),
                      structure_count=g['structure_count'], root_cases=root_plan(),
                      normal_forms=normal_forms(), global_lower_bound_proved=False)
    else:
        raise ValueError('Unknown proof stage')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
