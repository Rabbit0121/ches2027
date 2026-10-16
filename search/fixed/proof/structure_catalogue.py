"""Materialize all small structures; represent large domains by exact grammar.

Both operations are purely structural: no variable names or truth tables are
evaluated here. Grammar choice nodes are exact finite structure families, not
heuristic beam-width restrictions.
"""
from .runtime import run as _run, fail as _fail
import argparse, json, hashlib
from pathlib import Path
from .count_shapes import count, rows, INV_TAILS
from .structures import unrank
from .model import D

def catalogue(bound, path):
    nodes = []
    ids = {}
    gates = list(D)

    def intern(s):
        children = tuple((intern(c) for c in s[1:]))
        key = (s[0], children)
        if key in ids:
            return ids[key]
        i = len(nodes)
        ids[key] = i
        delay = D[s[0]] + (max((nodes[j]['delay'] for j in children)) if children else 0)
        nodes.append(dict(gate=gates.index(s[0]), children=children, delay=delay))
        return i
    n = count(bound, True)
    for i in range(n):
        intern(unrank(bound, i, True))
    assert len(nodes) == n
    payload = dict(status='ALL_NORMAL_STRUCTURES_ENUMERATED', bound_fs=bound, normal_form=True, structures=n, nodes=nodes, truth_tables_evaluated=0)
    raw = json.dumps(payload, separators=(',', ':')).encode()
    path.write_bytes(raw)
    return dict(bound_fs=bound, structures=n, sha256=hashlib.sha256(raw).hexdigest())

def grammar(bound, path):
    states = {}

    def visit(b):
        if b in states:
            return
        state = dict(bound_fs=b, count=str(count(b, True)), choices=[])
        states[b] = state
        for kind, g, n in rows(b, True):
            choice = dict(kind=kind, gate=g, count=str(n))
            if kind == 'gate':
                child = b - D[g]
                visit(child)
                choice['children_domain'] = child
                if g == 'INV':
                    choice['allowed_child_roots'] = INV_TAILS
                choice['symmetry'] = 'ordered' if g == 'MUX2' else 'pair_then_single' if g in ('AOI21', 'OAI21') else 'unordered_pair_of_unordered_pairs' if g in ('AOI22', 'OAI22') else 'unordered_multiset'
            state['choices'].append(choice)
        assert sum((int(q['count']) for q in state['choices'])) == int(state['count'])
    visit(bound)
    payload = dict(status='COMPLETE_FINITE_STRUCTURE_GRAMMAR', bound_fs=bound, normal_form=True, structure_count=str(count(bound, True)), states=[states[b] for b in sorted(states)], truth_tables_evaluated=0, global_lower_bound_proved=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return payload
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser()
        p.add_argument('--bound-fs', type=int, default=157297)
        p.add_argument('--output', required=True, type=Path)
        a = p.parse_args()
        r = grammar(a.bound_fs, a.output)
        print(json.dumps({k: v for k, v in r.items() if k != 'states'} | {'grammar_states': len(r['states'])}))
    except Exception as error:
        _fail(error)
