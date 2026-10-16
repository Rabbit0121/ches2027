"""Count all timing-feasible gate trees before assigning input variables.

Only actual gate-pin permutation symmetries are quotiented. Paid BUF/INV
leaves remain distinguished from internal unary gates. No truth library is
used, and no target-specific exclusion is inferred from these counts.
"""
from .runtime import run as _run, fail as _fail
import argparse
import json
import math
import itertools
from functools import lru_cache
from pathlib import Path
from .model import D, ARITY, gate

def inversion_rules():
    rules = {}
    for g in D:
        if g in ('BUF', 'INV'):
            continue
        options = [h for h in D if ARITY[h] == ARITY[g] and D[h] < D['INV'] + D[g] and all((gate(h, list(bits), 1) == 1 - gate(g, list(bits), 1) for bits in itertools.product((0, 1), repeat=ARITY[g])))]
        if options:
            rules[g] = min(options, key=D.get)
    return rules
INVERSE_REPLACEMENTS = inversion_rules()
INV_TAILS = tuple((g for g in D if g not in ('BUF', 'INV') and g not in INVERSE_REPLACEMENTS))

def multiset(n, k):
    return math.comb(n + k - 1, k) if n else 0

def arrangements(g, n):
    if g in ('INV', 'BUF'):
        return n
    if g in ('AOI21', 'OAI21'):
        return multiset(n, 2) * n
    if g in ('AOI22', 'OAI22'):
        return multiset(multiset(n, 2), 2)
    if g == 'MUX2':
        return n ** 3
    return multiset(n, ARITY[g])

@lru_cache(None)
def rows(bound, normal=False):
    if bound < min(D.values()):
        return ()
    result = [('leaf', g, 1) for g in ('BUF', 'INV') if D[g] <= bound]
    for g, d in D.items():
        if normal and g == 'BUF':
            continue
        if normal and g == 'INV':
            n = sum((q[2] for q in rows(bound - d, normal) if q[0] == 'gate' and q[1] in INV_TAILS))
        else:
            n = arrangements(g, count(bound - d, normal))
        if n:
            result.append(('gate', g, n))
    return tuple(result)

@lru_cache(None)
def count(bound, normal=False):
    return sum((q[2] for q in rows(bound, normal)))

def report(bound, normal=False):
    details = []
    for g, d in D.items():
        n = count(bound - d, normal)
        roots = sum((q[2] for q in rows(bound, normal) if q[:2] == ('gate', g)))
        details.append(dict(gate=g, child_deadline_fs=bound - d, child_shapes=str(n), internal_root_shapes=str(roots)))
    return dict(status='EXACT_STRUCTURE_COUNT_ONLY', bound_fs=bound, shapes=str(count(bound, normal)), normal_form=normal, paid_leaf_shapes=sum((D[g] <= bound for g in ('BUF', 'INV'))), symmetry='Full permutation for symmetric gates; first pair for AOI/OAI21; pair swaps and within-pair swaps for AOI/OAI22; MUX pins ordered', inverse_replacements=INVERSE_REPLACEMENTS if normal else {}, roots=details, global_lower_bound_proved=False)
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument('--bound-fs', type=int, default=157297)
        p.add_argument('--output', type=Path, required=True)
        p.add_argument('--normal', action='store_true')
        a = p.parse_args()
        r = report(a.bound_fs, a.normal)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(r, indent=2), encoding='utf-8')
        print(json.dumps(r, indent=2))
    except Exception as error:
        _fail(error)
