"""Extend a balanced component space, then select a complete implementation."""
from functools import lru_cache
import random
import time
from .crypto import linearity, uniformity, metrics


def construct(pool, config, seconds):
    s, n = pool.structures, pool.structures.problem.n
    deadline, rng = time.monotonic() + seconds, random.Random()

    @lru_cache(maxsize=262144)
    def admissible(f):
        return f.bit_count() == 1 << (n-1) and linearity(f, n) <= config['linearity']

    functions = sorted((f for f in pool.by_truth if admissible(f)),
                       key=lambda f: (pool.scores[pool.by_truth[f][0]], f))
    bests, seen = [], set()
    while len(functions) >= n and time.monotonic() < deadline:
        width = min(len(functions), max(n, int(len(functions) * rng.choice((.15, .35, 1.)))))
        first = rng.choice(functions[:width])
        selected, span = [first], [0, first]
        roots = [pool.by_truth[first][0]]
        available = [f for f in functions if f != first and admissible(f ^ first)]
        while len(selected) < n and available and time.monotonic() < deadline:
            width = max(1, int(len(available) * rng.choice((.2, .5, 1.))))
            if config['guided_width']:
                trials = []
                for f in rng.sample(available[:width], min(width, config['guided_width'])):
                    options = pool.by_truth[f]
                    for root in dict.fromkeys((options[0], rng.choice(options))):
                        if time.monotonic() >= deadline:
                            break
                        score = pool.measure(pool.graph(roots + [root]))['delay_ps']
                        trials.append((score + rng.random() * config['guided_jitter_ps'], f, root))
                if not trials:
                    break
                _, f, root = min(trials)
            else:
                f = rng.choice(available[:width])
                root = pool.by_truth[f][0]
            selected.append(f)
            roots.append(root)
            additions = [f ^ g for g in span]
            span += additions
            # Old coset tests are reused; test only the newly introduced coset.
            available = [h for h in available if h != f and all(admissible(h ^ g) for g in additions)]
        if len(selected) < n or time.monotonic() >= deadline:
            continue
        guided = dict(zip(selected, roots))
        selected.sort()
        key = tuple(selected)
        if key in seen:
            continue
        seen.add(key)
        table = [sum(((f >> x) & 1) << j for j, f in enumerate(selected)) for x in range(1 << n)]
        if uniformity(table) != config['uniformity'] or max(linearity(f, n) for f in span[1:]) != config['linearity']:
            continue
        best = None
        for attempt in range(config['joint_trials']):
            if time.monotonic() >= deadline:
                break
            roots = [guided[f] if attempt == 0 else pool.by_truth[f][0] if attempt == 1
                     else rng.choice(pool.by_truth[f]) for f in selected]
            graph = pool.graph(roots)
            measured = pool.measure(graph)
            if best is None or measured['delay_ps'] < best['delay_ps']:
                best = dict(lut=table, graph=graph, delay_ps=measured['delay_ps'],
                            expressions=[s.expression(i) for i in roots], cryptographic=metrics(table, n))
        if best is not None:
            bests.append(best)
            bests.sort(key=lambda b: b['delay_ps'])
            del bests[config['keep']:]
    return bests
