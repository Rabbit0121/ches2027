"""Exact rank/unrank of pin-symmetry classes of paid gate trees."""
from .runtime import run as _run, fail as _fail
import math
from functools import lru_cache
from itertools import groupby
from .model import D, ARITY, gate
from .count_shapes import count, rows, multiset, INV_TAILS

def unordered_unrank(n, k, index):
    """Colexicographic k-multisets, including repeated choices."""
    assert 0 <= index < multiset(n, k)
    out = [0] * k
    upper = n + k - 2
    for size in range(k, 0, -1):
        lo = size - 1
        hi = upper
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if math.comb(mid, size) <= index:
                lo = mid
            else:
                hi = mid - 1
        out[size - 1] = lo - (size - 1)
        index -= math.comb(lo, size)
        upper = lo - 1
    assert index == 0
    return tuple(out)

def canonical(g, children):
    c = list(children)
    if g in ('AOI21', 'OAI21'):
        c = sorted(c[:2]) + c[2:]
    elif g in ('AOI22', 'OAI22'):
        pairs = sorted((tuple(sorted(c[:2])), tuple(sorted(c[2:]))))
        c = list(pairs[0] + pairs[1])
    elif g != 'MUX2':
        c.sort()
    return (g, *c)

@lru_cache(maxsize=100000)
def unrank(bound, index, normal=True):
    assert 0 <= index < count(bound, normal)
    for kind, g, n in rows(bound, normal):
        if index >= n:
            index -= n
            continue
        if kind == 'leaf':
            return (g,)
        cut = bound - D[g]
        if normal and g == 'INV':
            offset = 0
            for typ, h, k in rows(cut, normal):
                if typ == 'gate' and h in INV_TAILS:
                    if index < k:
                        return ('INV', unrank(cut, offset + index, normal))
                    index -= k
                offset += k
            raise AssertionError('INV subdomain')
        m = count(cut, normal)
        if g in ('BUF', 'INV'):
            ids = (index,)
        elif g in ('AOI21', 'OAI21'):
            pair, third = divmod(index, m)
            ids = unordered_unrank(m, 2, pair) + (third,)
        elif g in ('AOI22', 'OAI22'):
            a, b = unordered_unrank(multiset(m, 2), 2, index)
            ids = unordered_unrank(m, 2, a) + unordered_unrank(m, 2, b)
        elif g == 'MUX2':
            index, c = divmod(index, m)
            a, b = divmod(index, m)
            ids = (a, b, c)
        else:
            ids = unordered_unrank(m, ARITY[g], index)
        return canonical(g, [unrank(cut, i, normal) for i in ids])
    raise AssertionError('structure rank')

def freeze(x):
    return tuple((freeze(v) if isinstance(v, list) else v for v in x))

@lru_cache(maxsize=100000)
def metrics(s):
    if len(s) == 1:
        return (D[s[0]], 1, 1)
    m = [metrics(c) for c in s[1:]]
    return (D[s[0]] + max((v[0] for v in m)), sum((v[1] for v in m)), 1 + sum((v[2] for v in m)))

@lru_cache(maxsize=100000)
def units(s):
    """Virtual PAIR nodes describe symmetry only; they are not circuit gates."""
    g = s[0]
    c = s[1:]
    if g in ('AOI21', 'OAI21'):
        return ((('PAIR', *c[:2]), c[2]), False)
    if g in ('AOI22', 'OAI22'):
        return ((('PAIR', *c[:2]), ('PAIR', *c[2:])), True)
    return (c, g != 'MUX2')

@lru_cache(maxsize=100000)
def layout(s, nvars):
    c, symmetric = units(s)
    if symmetric:
        return tuple(((child, len(list(group)), assignment_count(child, nvars)) for child, group in groupby(c)))
    return tuple(((child, 1, assignment_count(child, nvars)) for child in c))

@lru_cache(maxsize=100000)
def assignment_count(s, nvars=6):
    if len(s) == 1:
        return nvars
    return math.prod((multiset(n, k) for child, k, n in layout(s, nvars)))

def assignment_parts(s, index, nvars):
    assert 0 <= index < assignment_count(s, nvars)
    parts = []
    for child, k, n in layout(s, nvars):
        index, digit = divmod(index, multiset(n, k))
        ids = (digit,) if k == 1 else unordered_unrank(n, k, digit)
        parts.extend(((child, i) for i in ids))
    assert index == 0
    return parts

@lru_cache(maxsize=64)
def input_truths(nvars):
    return tuple((sum(((x >> i & 1) << x for x in range(1 << nvars))) for i in range(nvars)))

def evaluate(s, index, nvars=6):
    mask = (1 << (1 << nvars)) - 1
    if len(s) == 1:
        return gate(s[0], [input_truths(nvars)[index]], mask)
    vals = [evaluate_cached(child, i, nvars) for child, i in assignment_parts(s, index, nvars)]
    if s[0] == 'PAIR':
        return tuple(vals)
    if s[0] in ('AOI21', 'OAI21'):
        vals = list(vals[0]) + [vals[1]]
    if s[0] in ('AOI22', 'OAI22'):
        vals = list(vals[0]) + list(vals[1])
    return gate(s[0], vals, mask)
evaluate_cached = lru_cache(maxsize=100000)(evaluate)

def instantiate(s, index, nvars=6):
    if len(s) == 1:
        return [s[0], f'x{index}']
    vals = [instantiate(child, i, nvars) for child, i in assignment_parts(s, index, nvars)]
    if s[0] == 'PAIR':
        return tuple(vals)
    if s[0] in ('AOI21', 'OAI21'):
        vals = list(vals[0]) + [vals[1]]
    if s[0] in ('AOI22', 'OAI22'):
        vals = list(vals[0]) + list(vals[1])
    return [s[0], *vals]

def root_ranges(bound, normal=True, root=None):
    offset = 0
    result = []
    for typ, g, n in rows(bound, normal):
        if root is None or g == root:
            result.append((offset, n))
        offset += n
    return result

def global_rank(ranges, index):
    for offset, n in ranges:
        if index < n:
            return offset + index
        index -= n
    raise IndexError(index)
