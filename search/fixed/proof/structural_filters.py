"""Necessary target conditions using structure only, before variable assignment."""
from .runtime import run as _run, fail as _fail
from functools import lru_cache
from .model import D, ARITY, gate

def characteristics(truth, nvars):
    values = [truth >> x & 1 for x in range(1 << nvars)]
    anf = values.copy()
    for i in range(nvars):
        for x in range(1 << nvars):
            if x >> i & 1:
                anf[x] ^= anf[x ^ 1 << i]
    support = binate = 0
    for i in range(nvars):
        up = down = False
        for x in range(1 << nvars):
            if x >> i & 1:
                continue
            up |= values[x] < values[x | 1 << i]
            down |= values[x] > values[x | 1 << i]
        support += up or down
        binate += up and down
    return dict(support=support, binate=binate, degree=max((x.bit_count() for x, v in enumerate(anf) if v), default=0))

@lru_cache(None)
def gate_properties(g):
    n = ARITY[g]
    vals = [gate(g, [x >> i & 1 for i in range(n)], 1) for x in range(1 << n)]
    anf = vals.copy()
    for i in range(n):
        for x in range(1 << n):
            if x >> i & 1:
                anf[x] ^= anf[x ^ 1 << i]
    signs = []
    for i in range(n):
        up = any((vals[x] < vals[x | 1 << i] for x in range(1 << n) if not x >> i & 1))
        down = any((vals[x] > vals[x | 1 << i] for x in range(1 << n) if not x >> i & 1))
        signs.append(0 if up and down else 1 if up else -1 if down else None)
    return (tuple((x for x, v in enumerate(anf) if v)), tuple(signs))

@lru_cache(maxsize=100000)
def bounds(s):
    if len(s) == 1:
        return dict(leaves=1, degree=1, positive=int(s[0] == 'BUF'), negative=int(s[0] == 'INV'), unknown=0, binate_capacity=0)
    children = [bounds(c) for c in s[1:]]
    terms, signs = gate_properties(s[0])
    degree = max((sum((c['degree'] for i, c in enumerate(children) if t >> i & 1)) for t in terms), default=0)
    pos = neg = unknown = 0
    for sign, c in zip(signs, children):
        if sign == 1:
            pos += c['positive']
            neg += c['negative']
            unknown += c['unknown']
        elif sign == -1:
            pos += c['negative']
            neg += c['positive']
            unknown += c['unknown']
        elif sign == 0:
            unknown += c['leaves']
    return dict(leaves=sum((c['leaves'] for c in children)), degree=degree, positive=pos, negative=neg, unknown=unknown, binate_capacity=unknown + min(pos, neg))

def rejection(shape, target):
    b = bounds(shape)
    if b['leaves'] < target['support']:
        return 'insufficient_leaves'
    if b['degree'] < target['degree']:
        return 'insufficient_degree'
    if b['binate_capacity'] < target['binate']:
        return 'insufficient_binate_capacity'
    return None
