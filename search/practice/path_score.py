"""Characterized gate sequences rank proposals; complete graphs decide acceptance."""
import random
from weakref import WeakKeyDictionary
from ...core.structure import ARITY, physical_pins


class PathTable:
    def __init__(self, measure, max_depth=4, budget=64, load_ff=5.):
        self.measure, self.max_depth, self.budget = measure, max_depth, budget
        self.load_ff, self.cache = load_ff, {}
        self.structure_paths = WeakKeyDictionary()

    def get(self, sequence, create=True):
        sequence = tuple(sequence)
        if not sequence or len(sequence) + 1 > self.max_depth:
            return None
        if sequence not in self.cache:
            if not create or len(self.cache) >= self.budget:
                return None
            self.cache[sequence] = self.measure(test_structure(sequence, load_ff=self.load_ff))['delay_ps']
        return self.cache[sequence]

    def paths(self, structures, root):
        node = structures.nodes[root]
        if node.depth > self.max_depth:
            return None
        cache = self.structure_paths.setdefault(structures, {})
        if root not in cache:
            if node.kind in ('BUF', 'INV') and node.args[0] < 0:
                cache[root] = {()}
            else:
                paths = set()
                for child in node.args:
                    sub = self.paths(structures, child)
                    if sub is None:
                        return None
                    paths.update(p + (node.kind,) for p in sub)
                cache[root] = paths
        return cache[root]

    def lookup_structure(self, structures, root):
        paths = self.paths(structures, root)
        if not paths or () in paths:
            return None
        scores = [self.get(p) for p in sorted(paths)]
        return max(scores) if all(v is not None for v in scores) else None

    def extended_score(self, structures, root, kind):
        paths = self.paths(structures, root)
        if paths is None:
            return None
        scores = [self.get(p + (kind,), create=False) for p in sorted(paths)]
        return max(scores) if scores and all(v is not None for v in scores) else None

def test_structure(sequence, seed=0, load_ff=5.0, max_gates=20000):
    seq = tuple(sequence)
    if not seq or any((g not in ARITY for g in seq)):
        raise ValueError('Invalid gate sequence')
    m = 1
    for g in seq:
        m *= ARITY[g]
    per_tree = m
    level = m
    for g in seq:
        level //= ARITY[g]
        per_tree += level
    if m * per_tree > max_gates:
        raise ValueError('Path test structure exceeds gate budget')
    rng = random.Random(seed)
    rows = []
    outputs = []
    for replica in range(m):
        signals = []
        for x in range(m):
            signals.append(m + len(rows))
            rows.append(dict(cell=rng.choice(['BUF_X1', 'INV_X1']), pins={'A': x}))
        for kind in seq:
            parents = []
            arity = ARITY[kind]
            for k in range(0, len(signals), arity):
                parents.append(m + len(rows))
                rows.append(dict(cell=kind + '_X1', pins=dict(zip(physical_pins(kind), signals[k:k + arity]))))
            signals = parents
        assert len(signals) == 1
        outputs.append(dict(node=signals[0], load_ff=float(load_ff)))
    return dict(n_inputs=m, gates=rows, outputs=outputs)
