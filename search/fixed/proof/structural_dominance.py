"""Certified, input-label-independent containment of structure languages.

S <= T means every assignment to S can be simulated by an assignment to T.
Certificates use only Boolean identities on root pins, duplication, paid
constant subtrees, and recursively certified child simulations. No 6-variable
function library is constructed in this stage.
"""
from .runtime import run as _run, fail as _fail
import argparse, itertools, json, math, time
from functools import lru_cache
from pathlib import Path
from .model import D, ARITY, gate
from .structures import canonical

@lru_cache(None)
def truth_variables(k):
    return tuple((sum(((x >> i & 1) << x for x in range(1 << k))) for i in range(k)))

@lru_cache(None)
def minor_rules(source_gate, target_gate, negate):
    k = ARITY[source_gate]
    m = ARITY[target_gate]
    if m < k:
        return ()
    mask = (1 << (1 << k)) - 1
    vs = truth_variables(k)
    literals = tuple((v for a in vs for v in (a, a ^ mask))) + (0, mask)
    wanted = gate(source_gate, list(vs), mask) ^ (mask if negate else 0)
    rules = []
    for mapping in itertools.product(range(len(literals)), repeat=m):
        if {j // 2 for j in mapping if j < 2 * k} != set(range(k)):
            continue
        if gate(target_gate, [literals[j] for j in mapping], mask) == wanted:
            rules.append(mapping)
    return tuple(rules)

@lru_cache(None)
def projection_rules(g, negate):
    wanted = 1 if negate else 2
    literals = (2, 1, 0, 3)
    return tuple((q for q in itertools.product(range(4), repeat=ARITY[g]) if any((j < 2 for j in q)) and gate(g, [literals[j] for j in q], 3) == wanted))

class Structures:

    def __init__(self):
        self.nodes = []
        self.ids = {}

    def add(self, g, children=()):
        key = canonical(g, children)
        if key in self.ids:
            return self.ids[key]
        c = key[1:]
        if not c:
            assert g in ('BUF', 'INV')
            delay = D[g]
            leaves = 1
            unary = 2 if g == 'BUF' else 1
        else:
            delay = D[g] + max((self.nodes[i]['delay'] for i in c))
            leaves = sum((self.nodes[i]['leaves'] for i in c))
            unary = gate(g, [self.nodes[i]['unary'] for i in c], 3)
        i = len(self.nodes)
        self.ids[key] = i
        self.nodes.append(dict(gate=g, children=c, delay=delay, leaves=leaves, unary=unary))
        return i

    def shape(self, i):
        n = self.nodes[i]
        return (n['gate'], *(self.shape(j) for j in n['children']))

class Simulation:

    def __init__(self, structures):
        self.s = structures
        self.cache = {}
        self.proofs = {}
        self.tests = 0

    def sim(self, a, b, neg=0):
        key = (a, b, neg)
        if key in self.cache:
            return self.cache[key]
        self.tests += 1
        x = self.s.nodes[a]
        y = self.s.nodes[b]
        proof = None
        if a == b and (not neg):
            proof = dict(kind='identity')
        elif len(x['children']) == 0:
            if y['unary'] == x['unary'] ^ (3 if neg else 0):
                proof = dict(kind='one_variable_assignment')
        elif y['leaves'] >= x['leaves'] and y['children']:
            rules = projection_rules(y['gate'], neg)
            for mapping in rules:
                if all((self.s.nodes[t]['unary'] == (0 if code == 2 else 3) if code >= 2 else self.sim(a, t, code) for t, code in zip(y['children'], mapping))):
                    proof = dict(kind='projection', mapping=mapping)
                    break
            if proof is None:
                k = len(x['children'])
                for mapping in minor_rules(x['gate'], y['gate'], neg):
                    if all((self.s.nodes[t]['unary'] == (0 if code == 2 * k else 3) if code >= 2 * k else self.sim(x['children'][code // 2], t, code % 2) for t, code in zip(y['children'], mapping))):
                        proof = dict(kind='root_minor', mapping=mapping)
                        break
        value = proof is not None
        self.cache[key] = value
        if value:
            self.proofs[key] = proof
        return value

    def verify(self):
        checked = set()
        active = set()

        def visit(key):
            if key in checked:
                return
            assert key not in active
            active.add(key)
            a, b, neg = key
            x = self.s.nodes[a]
            y = self.s.nodes[b]
            p = self.proofs[key]
            if p['kind'] == 'identity':
                assert a == b and neg == 0
            elif p['kind'] == 'one_variable_assignment':
                assert not x['children'] and y['unary'] == x['unary'] ^ (3 if neg else 0)
            else:
                whole = p['kind'] == 'projection'
                assert whole or p['kind'] == 'root_minor'
                source = (a,) if whole else x['children']
                k = len(source)
                mask = (1 << (1 << k)) - 1
                vs = truth_variables(k)
                args = []
                for target, code in zip(y['children'], p['mapping']):
                    if code >= 2 * k:
                        bit = int(code == 2 * k + 1)
                        assert code in (2 * k, 2 * k + 1)
                        assert self.s.nodes[target]['unary'] == 3 * bit
                        args.append(mask * bit)
                    else:
                        i, sign = divmod(code, 2)
                        visit((source[i], target, sign))
                        args.append(vs[i] ^ (mask if sign else 0))
                assert len(args) == len(y['children'])
                expected = (vs[0] if whole else gate(x['gate'], list(vs), mask)) ^ (mask if neg else 0)
                assert gate(y['gate'], args, mask) == expected
            active.remove(key)
            checked.add(key)
        for key in self.proofs:
            visit(key)
        return len(checked)

class CandidateLimit(Exception):
    pass

class Builder:

    def __init__(self, out, limit=0):
        self.s = Structures()
        self.sim = Simulation(self.s)
        self.memo = {}
        self.out = out
        self.limit = limit
        self.candidates = 0
        self.start = time.time()
        self.records = []

    def tuples(self, g, ids):
        k = ARITY[g]
        if g in ('BUF', 'INV'):
            yield from ((i,) for i in ids)
        elif g in ('AOI21', 'OAI21'):
            for pair in itertools.combinations_with_replacement(ids, 2):
                for last in ids:
                    yield (*pair, last)
        elif g in ('AOI22', 'OAI22'):
            pairs = list(itertools.combinations_with_replacement(ids, 2))
            for a, b in itertools.combinations_with_replacement(pairs, 2):
                yield (a + b)
        elif g == 'MUX2':
            yield from itertools.product(ids, repeat=3)
        else:
            yield from itertools.combinations_with_replacement(ids, k)

    def build(self, bound):
        if bound in self.memo:
            return self.memo[bound]
        if bound < min(D.values()):
            self.memo[bound] = ()
            return ()
        frontier = []
        dominated = {}
        generated = 0

        def add(i):
            nonlocal frontier, generated
            generated += 1
            self.candidates += 1
            if self.limit and self.candidates > self.limit:
                raise CandidateLimit('Explicit candidate experiment limit')
            for j in frontier:
                if self.sim.sim(i, j):
                    dominated[i] = j
                    return
            keep = []
            for j in frontier:
                if self.sim.sim(j, i):
                    dominated[j] = i
                else:
                    keep.append(j)
            keep.append(i)
            frontier = keep
        for g in ('BUF', 'INV'):
            if D[g] <= bound:
                add(self.s.add(g))
        for g, fee in D.items():
            children = self.build(bound - fee)
            for c in self.tuples(g, children):
                add(self.s.add(g, c))
        assert all((self.s.nodes[i]['delay'] <= bound for i in frontier))
        rec = dict(bound=bound, generated=generated, frontier=len(frontier), representatives=frontier, replacements=[(a, b) for a, b in dominated.items() if a != b])
        self.records.append(rec)
        self.memo[bound] = tuple(frontier)
        with (self.out / 'progress.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')
        print(f'bound={bound} candidates={generated} frontier={len(frontier)} cumulative={self.candidates} seconds={time.time() - self.start:.3f}', flush=True)
        return self.memo[bound]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bound-fs', type=int, default=100883)
    p.add_argument('--candidate-limit', type=int, default=0)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    b = Builder(a.output, a.candidate_limit)
    r = dict(status='PARTIAL', bound_fs=a.bound_fs, global_lower_bound_proved=False)
    try:
        frontier = b.build(a.bound_fs)
        checked = b.sim.verify()
        r.update(status='COMPLETE_STRUCTURAL_DOMINANCE_BASIS', representatives=frontier, frontier=len(frontier), verified_simulations=checked)
    except CandidateLimit as e:
        r['reason'] = str(e)
    r.update(candidates=b.candidates, interned_structures=len(b.s.nodes), simulation_tests=b.sim.tests, seconds=time.time() - b.start)
    (a.output / 'nodes.json').write_text(json.dumps(b.s.nodes), encoding='utf-8')
    proofs = [dict(source=a, target=t, neg=neg, **proof) for (a, t, neg), proof in b.sim.proofs.items()]
    (a.output / 'simulations.json').write_text(json.dumps(proofs), encoding='utf-8')
    (a.output / 'status.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    print(json.dumps(r, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
