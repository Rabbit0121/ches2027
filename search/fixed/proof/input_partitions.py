"""Quotient simultaneous variable renaming; test the full target orbit.

This is a search symmetry, not permission to change the fixed target. A hit
is mapped back to the original six variables and independently re-evaluated.
"""
from .runtime import run as _run, fail as _fail
import itertools
from functools import lru_cache
from .model import gate
from .structures import input_truths

@lru_cache(None)
def completions(remaining, used, nvars):
    if remaining == 0:
        return int(used == nvars)
    if used > nvars or used + remaining < nvars:
        return 0
    return used * completions(remaining - 1, used, nvars) + (completions(remaining - 1, used + 1, nvars) if used < nvars else 0)

def partition_count(leaves, nvars=6):
    return completions(leaves, 0, nvars)

def partition_unrank(leaves, index, nvars=6):
    assert 0 <= index < partition_count(leaves, nvars)
    result = []
    used = 0
    for remaining in range(leaves - 1, -1, -1):
        old = completions(remaining, used, nvars)
        if index < used * old:
            label, index = divmod(index, old)
            result.append(label)
        else:
            index -= used * old
            assert used < nvars
            result.append(used)
            used += 1
    assert used == nvars and index == 0
    return tuple(result)

@lru_cache(None)
def target_orbit(target, nvars=6):
    result = {}
    for perm in itertools.permutations(range(nvars)):
        h = 0
        for z in range(1 << nvars):
            x = sum(((z >> i & 1) << perm[i] for i in range(nvars)))
            h |= (target >> x & 1) << z
        result.setdefault(h, perm)
    return result

@lru_cache(maxsize=10000)
def compile_shape(s):
    rows = []
    leaf = 0

    def add(q):
        nonlocal leaf
        if len(q) == 1:
            row = (q[0], leaf, None)
            leaf += 1
        else:
            row = (q[0], None, tuple((add(c) for c in q[1:])))
        index = len(rows)
        rows.append(row)
        return index
    add(s)
    return tuple(rows)

def evaluate_labels(shape, labels, nvars=6):
    values = []
    pi = input_truths(nvars)
    mask = (1 << (1 << nvars)) - 1
    for g, leaf, children in compile_shape(shape):
        args = [pi[labels[leaf]]] if leaf is not None else [values[i] for i in children]
        values.append(gate(g, args, mask))
    return values[-1]

def instantiate_labels(shape, labels):
    it = iter(labels)

    def visit(q):
        return [q[0], f'x{next(it)}'] if len(q) == 1 else [q[0], *(visit(c) for c in q[1:])]
    return visit(shape)
