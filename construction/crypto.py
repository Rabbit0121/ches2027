"""Exact truth-table cryptographic checks; bit zero is the least significant bit."""
from functools import lru_cache

def walsh(truth, n):
    a = [1 - 2 * ((truth >> x) & 1) for x in range(1 << n)]
    step = 1
    while step < len(a):
        for k in range(0, len(a), 2 * step):
            for j in range(k, k + step):
                u, v = a[j], a[j + step]
                a[j], a[j + step] = u + v, u - v
        step *= 2
    return a

@lru_cache(maxsize=262144)
def linearity(truth, n):
    return max(map(abs, walsh(truth, n)))

@lru_cache(maxsize=262144)
def degree(truth, n):
    a = [(truth >> x) & 1 for x in range(1 << n)]
    for j in range(n):
        for x in range(1 << n):
            if x & (1 << j):
                a[x] ^= a[x ^ (1 << j)]
    return max((x.bit_count() for x, bit in enumerate(a) if bit), default=0)

def components(table, n):
    coordinates = [sum(((v >> j) & 1) << x for x, v in enumerate(table)) for j in range(n)]
    span = [0]
    for f in coordinates:
        span += [f ^ g for g in span]
    return coordinates, span[1:]

def uniformity(table):
    size = len(table)
    result = 0
    for delta in range(1, size):
        counts = [0] * size
        for x in range(size):
            counts[table[x] ^ table[x ^ delta]] += 1
        result = max(result, max(counts))
    return result

def metrics(table, n):
    assert len(table) == 1 << n and all(0 <= v < 1 << n for v in table)
    coords, span = components(table, n)
    degrees = [degree(f, n) for f in span]
    return dict(bijective=len(set(table)) == 1 << n,
                uniformity=uniformity(table), linearity=max(linearity(f, n) for f in span),
                coordinate_degrees_lsb=[degree(f, n) for f in coords],
                component_degree_min=min(degrees), component_degree_max=max(degrees),
                all_components_balanced=all(f.bit_count() == 1 << (n - 1) for f in span))

def lut(roots, structures):
    return [sum(((structures.truth(i) >> x) & 1) << j for j, i in enumerate(roots))
            for x in range(1 << structures.problem.n)]
