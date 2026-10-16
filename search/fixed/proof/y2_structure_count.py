"""Count entire structure families rejected by Y2's six binate variables.

The profile counts positive, negative, and non-unate-path leaf occurrences,
each saturated at six. Equal profiles are counted with multiplicities, not
identified as equal structures. This remains a structure-only computation.
"""
from .runtime import run as _run, fail as _fail
import argparse, itertools, json, math, time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from .model import D, ARITY, S
from .count_shapes import count, INV_TAILS
from .structural_filters import characteristics

def plus(a, b):
    return tuple((min(6, x + y) for x, y in zip(a, b)))

def flip(a):
    return (a[1], a[0], a[2])

def freeze(c):
    return tuple(sorted(c.items()))

@lru_cache(maxsize=None)
def symmetric(pool, k):
    out = Counter()
    for indices in itertools.combinations_with_replacement(range(len(pool)), k):
        profile = (0, 0, 0)
        ways = 1
        for i, group in itertools.groupby(indices):
            m = len(list(group))
            p, w = pool[i]
            ways *= math.comb(w + m - 1, m)
            for _ in range(m):
                profile = plus(profile, p)
        out[profile] += ways
    return freeze(out)

def ordered(a, b):
    out = Counter()
    for p, w in a:
        for q, v in b:
            out[plus(p, q)] += w * v
    return freeze(out)

@lru_cache(None)
def families(bound):
    if bound < min(D.values()):
        return ()
    result = []
    for g in ('BUF', 'INV'):
        if D[g] <= bound:
            result.append(('leaf_' + g, (((1, 0, 0) if g == 'BUF' else (0, 1, 0), 1),)))
    for g, d in D.items():
        if g == 'BUF':
            continue
        if g == 'INV':
            c = Counter()
            for h, pool in families(bound - d):
                if h in INV_TAILS:
                    for p, w in pool:
                        c[flip(p)] += w
            result.append((g, freeze(c)))
            continue
        pool = profiles(bound - d)
        if not pool:
            continue
        if g in ('AOI21', 'OAI21'):
            part = ordered(symmetric(pool, 2), pool)
        elif g in ('AOI22', 'OAI22'):
            part = symmetric(symmetric(pool, 2), 2)
        elif g == 'MUX2':
            selector = Counter()
            for p, w in pool:
                selector[0, 0, min(6, sum(p))] += w
            part = ordered(ordered(pool, pool), freeze(selector))
        else:
            part = symmetric(pool, ARITY[g])
        if g in ('XOR2', 'XNOR2'):
            c = Counter()
            for p, w in part:
                c[0, 0, min(6, sum(p))] += w
            part = freeze(c)
        elif g.startswith(('NAND', 'NOR', 'AOI', 'OAI')):
            part = tuple(((flip(p), w) for p, w in part))
        result.append((g, part))
    return tuple(result)

@lru_cache(None)
def profiles(bound):
    c = Counter()
    for _, pool in families(bound):
        c.update(dict(pool))
    return freeze(c)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bound-fs', type=int, default=157297)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    start = time.time()
    target = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    needed = characteristics(target, 6)['binate']
    assert needed == 6
    pool = profiles(a.bound_fs)
    total = sum((w for _, w in pool))
    assert total == count(a.bound_fs, True)
    survivors = sum((w for (p, n, u), w in pool if u + min(p, n) >= needed))
    rows = []
    for g, entries in families(a.bound_fs):
        rows.append(dict(root=g, total=str(sum((w for _, w in entries))), surviving_necessary_condition=str(sum((w for (p, n, u), w in entries if u + min(p, n) >= needed)))))
    result = dict(status='EXACT_Y2_STRUCTURE_FAMILY_COUNT', bound_fs=a.bound_fs, normal_shapes=str(total), structurally_excluded=str(total - survivors), surviving_necessary_condition=str(survivors), profile_count=len(pool), target_y2=target, target_binate_variables=needed, roots=rows, seconds=time.time() - start, global_lower_bound_proved=False)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
