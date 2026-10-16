"""Independent small Cartesian enumerations test structure and label orbits."""
from .runtime import run as _run, fail as _fail
import argparse, itertools, json, random, time
from functools import lru_cache
from pathlib import Path
from .model import D, ARITY, gate, S
from .count_shapes import count, INV_TAILS, INVERSE_REPLACEMENTS
from .structures import canonical, unrank, metrics, unordered_unrank, assignment_count, evaluate, instantiate
from .structural_filters import bounds, characteristics
from .input_partitions import partition_count, partition_unrank, evaluate_labels, target_orbit, instantiate_labels
from .beam_truths import Engine, ExpansionLimit
from collections import Counter
from .y2_structure_count import profiles

@lru_cache(None)
def brute_shapes(bound, normal):
    result = {(g,) for g in ('BUF', 'INV') if D[g] <= bound}
    if bound < min(D.values()):
        return frozenset()
    for g, d in D.items():
        if normal and g == 'BUF':
            continue
        children = brute_shapes(bound - d, normal)
        for c in itertools.product(children, repeat=ARITY[g]):
            if normal and g == 'INV' and (not (len(c[0]) > 1 and c[0][0] in INV_TAILS)):
                continue
            result.add(canonical(g, c))
    return frozenset(result)

def decorate(shape, labels):
    if len(shape) == 1:
        return (shape[0], f'x{next(labels)}')
    return (shape[0], *(decorate(c, labels) for c in shape[1:]))

def canon_expr(e):
    if isinstance(e, str):
        return e
    g = e[0]
    c = [canon_expr(x) for x in e[1:]]
    if g in ('AOI21', 'OAI21'):
        c = sorted(c[:2], key=repr) + c[2:]
    elif g in ('AOI22', 'OAI22'):
        pairs = sorted((tuple(sorted(c[:2], key=repr)), tuple(sorted(c[2:], key=repr))), key=repr)
        c = list(pairs[0] + pairs[1])
    elif g != 'MUX2':
        c.sort(key=repr)
    return (g, *c)

def scalar_truth(e, nvars):

    def bit(q, x):
        if isinstance(q, str):
            return x >> int(q[1:]) & 1
        return gate(q[0], [bit(c, x) for c in q[1:]], 1)
    return sum((bit(e, x) << x for x in range(1 << nvars)))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    start = time.time()
    checks = 0
    for n in range(1, 9):
        for k in range(1, 5):
            oracle = set(itertools.combinations_with_replacement(range(n), k))
            got = {unordered_unrank(n, k, i) for i in range(len(oracle))}
            assert got == oracle
            checks += 1
    for normal in (False, True):
        for bound in (22047, 22048, 33557, 44100, 60000, 73027, 80000):
            expected = brute_shapes(bound, normal)
            n = count(bound, normal)
            got = [unrank(bound, i, normal) for i in range(n)]
            assert len(set(got)) == n and set(got) == set(expected)
            assert all((metrics(s)[0] <= bound for s in got))
            checks += 1
    b = ('BUF',)
    v = ('INV',)
    samples = [canonical(g, [b] * ARITY[g]) for g in D]
    samples += [canonical(g, [b if i % 2 else v for i in range(ARITY[g])]) for g in D]
    samples += [('AOI22', ('NAND2', b, b), v, ('NAND2', b, b), v), ('OAI21', ('NAND2', b, b), ('NAND2', b, b), v), ('NAND3', ('INV', v), ('INV', v), ('BUF', b)), ('MUX2', ('NAND2', b, v), ('NAND2', b, v), v)]
    for s in samples:
        s = canonical(s[0], s[1:])
        leaves = metrics(s)[1]
        expected = {canon_expr(decorate(s, iter(labels))) for labels in itertools.product(range(2), repeat=leaves)}
        n = assignment_count(s, 2)
        actual = set()
        for i in range(n):
            e = instantiate(s, i, 2)
            actual.add(canon_expr(e))
            assert evaluate(s, i, 2) == scalar_truth(e, 2)
            actual_properties = characteristics(evaluate(s, i, 2), 2)
            limit = bounds(s)
            assert actual_properties['degree'] <= limit['degree']
            assert actual_properties['binate'] <= limit['binate_capacity']
        assert len(actual) == n and actual == expected
        checks += 1
    example = ('NAND4', *(('NAND3', b, b, b),) * 4)
    assert assignment_count(example) == 455126 and metrics(example)[0] == 112811
    assert len(INVERSE_REPLACEMENTS) == 12 and len(INV_TAILS) == 7
    s = ('XOR2', b, v)
    target = scalar_truth(['XOR2', ['BUF', 'x0'], ['INV', 'x1']], 6)
    assert any((evaluate(s, i) == target for i in range(assignment_count(s))))
    for leaves in range(1, 8):
        for variables in range(1, min(4, leaves) + 1):

            def restricted(labels):
                seen = {}
                return tuple((seen.setdefault(i, len(seen)) for i in labels))
            expected = {restricted(labels) for labels in itertools.product(range(variables), repeat=leaves) if len(set(labels)) == variables}
            got = {partition_unrank(leaves, i, variables) for i in range(partition_count(leaves, variables))}
            assert expected == got
            checks += 1
    for s in samples[:21]:
        leaves = metrics(s)[1]
        if leaves < 2:
            continue
        expected = {scalar_truth(decorate(s, iter(labels)), 2) for labels in itertools.product(range(2), repeat=leaves) if len(set(labels)) == 2}
        expanded = set()
        for i in range(partition_count(leaves, 2)):
            labels = partition_unrank(leaves, i, 2)
            truth = evaluate_labels(s, labels, 2)
            assert truth == scalar_truth(instantiate_labels(s, labels), 2)
            expanded.update(target_orbit(truth, 2))
        assert expanded == expected
        checks += 1
    engine = Engine(nvars=2)
    for s in samples:
        expected = {scalar_truth(decorate(s, iter(labels)), 2) for labels in itertools.product(range(2), repeat=metrics(s)[1])}
        actual = engine.expand(s)
        assert set(actual) == expected
        for f, e in actual.items():
            assert scalar_truth(e, 2) == f
        for target in range(16):
            witness = engine.match(s, target)
            assert (witness is not None) == (target in expected)
            if witness is not None:
                assert scalar_truth(witness, 2) == target
        checks += 1
    try:
        Engine(max_functions=1).expand(('NAND2', b, b))
    except ExpansionLimit:
        pass
    else:
        raise AssertionError('Limit must not return a complete result')
    y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    for h, perm in target_orbit(y).items():
        restored = sum(((h >> sum(((x >> perm[i] & 1) << i for i in range(6))) & 1) << x for x in range(64)))
        assert restored == y
    checks += 1
    for bound in (60000, 84278, 100883):
        expected = Counter()
        for i in range(count(bound, True)):
            bnd = bounds(unrank(bound, i, True))
            expected[tuple((min(6, bnd[key]) for key in ('positive', 'negative', 'unknown')))] += 1
        assert expected == dict(profiles(bound))
        checks += 1
    r = dict(status='PASS', checks=checks + 2, structure_oracle='Full ordered Cartesian product, then canonicalize', assignment_oracle='All ordered variable labels, then canonicalize; independent scalar truth evaluation', example_orbits=455126, example_delay_fs=112811, seconds=time.time() - start)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(r, indent=2), encoding='utf-8')
    print(json.dumps(r))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
