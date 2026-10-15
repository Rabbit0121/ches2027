"""Generate low-delay coordinates and keep alternative root decompositions."""
from itertools import product
import json
import random
import time
from ..core.model import Problem, ARITY
from ..core.structure import Structures


class Pool:
    def __init__(self, bits, costs, measure, paths=None, depth=5, width=16, load_ff=5.):
        problem = Problem('coordinates', bits, bits, list(range(1 << bits)), costs)
        self.structures = Structures(problem)
        self.measure, self.paths, self.depth, self.width = measure, paths, depth, width
        self.load_ff, self.by_truth, self.scores, self.seen = load_ff, {}, {}, set()
        self.literals = [self.structures.make(kind, (-i-1,))
                         for i in range(bits) for kind in ('BUF', 'INV')]

    def graph(self, roots):
        return self.structures.graph(roots, self.load_ff)[0]

    def offer(self, root):
        if root in self.seen:
            return
        self.seen.add(root)
        node = self.structures.nodes[root]
        if node.depth > self.depth:
            return
        score = self.paths.lookup_structure(self.structures, root) if self.paths else None
        if score is None:
            score = self.measure(self.graph([root]))['delay_ps']
        self.scores[root] = score
        variants = self.by_truth.setdefault(node.truth, [])
        candidates = sorted(variants + [root], key=lambda i: (self.scores[i], len(self.structures.descendants(i)), i))
        retained = candidates[:min(2, self.width)]
        def decomposition(i):
            node = self.structures.nodes[i]
            return node.kind, tuple(sorted(self.structures.truth(a) for a in node.args))
        signatures = {decomposition(i) for i in retained}
        for i in candidates:
            if len(retained) >= self.width:
                break
            if decomposition(i) not in signatures:
                retained.append(i)
                signatures.add(decomposition(i))
        for i in candidates:
            if len(retained) >= self.width:
                break
            if i not in retained:
                retained.append(i)
        variants[:] = sorted(retained, key=lambda i: (self.scores[i], i))

    def generate(self, seconds):
        deadline = time.monotonic() + seconds
        rng = random.Random()
        for root in self.literals:
            self.offer(root)
        for kind in self.structures.problem.costs:
            if kind in ('BUF', 'INV'):
                continue
            for args in product(self.literals, repeat=ARITY[kind]):
                if time.monotonic() >= deadline:
                    return self
                self.offer(self.structures.make(kind, args))
        choices, step = [], 0
        while time.monotonic() < deadline:
            if step % 1000 == 0:
                choices = [i for ids in self.by_truth.values() for i in ids]
            kind = rng.choice(list(self.structures.problem.costs))
            args = [rng.choice(self.literals if rng.random() < .65 else choices)
                    for _ in range(ARITY[kind])]
            # Reject by depth before allocating a new physical node.
            if 1 + max(self.structures.nodes[i].depth for i in args) <= self.depth:
                self.offer(self.structures.make(kind, args))
            step += 1
        return self

    def save(self, path):
        data = [dict(truth=str(f), variants=[dict(expression=self.structures.expression(i),
                                                score_ps=self.scores[i]) for i in ids])
                for f, ids in sorted(self.by_truth.items())]
        path.write_text(json.dumps(data, indent=2) + '\n')
