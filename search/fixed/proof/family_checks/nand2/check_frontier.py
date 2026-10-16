"""Rebuild the weighted-triple partition independently in Python."""
from ...runtime import run as _run, fail as _fail
import argparse, json, math, struct
from pathlib import Path
from ...family_checks.nand2.fresh_exceptions import Y, Z, THRESHOLD, weight, read_rows

def verify(folder):
    rows = sorted((f for f, t in read_rows(folder / 'reduced.bin') if weight(f) >= THRESHOLD), key=lambda f: (f & Z, f))
    assert len(rows) == len(set(rows))
    nodes = []

    def build(lo, hi):
        at = len(nodes)
        nodes.append(None)
        if hi - lo == 1:
            q = (lo, hi, -1, -1, rows[lo] & Z, rows[lo] & Y)
        else:
            diff = (rows[lo] ^ rows[hi - 1]) & Z
            if not diff:
                diff = rows[lo] ^ rows[hi - 1]
            bit = diff.bit_length() - 1
            a, b = (lo, hi)
            while a < b:
                m = (a + b) // 2
                if rows[m] >> bit & 1:
                    b = m
                else:
                    a = m + 1
            assert lo < a < hi
            left, right = (build(lo, a), build(a, hi))
            q = (lo, hi, left, right, nodes[left][4] & nodes[right][4], nodes[left][5] | nodes[right][5])
        nodes[at] = q
        return at
    if rows:
        build(0, len(rows))

    def alive(t):
        a, b, c = (nodes[i] for i in t)
        return not a[4] & b[4] & c[4] and weight(a[5] & b[5] & c[5]) >= THRESHOLD

    def cardinality(t):
        a, b, c = t
        n = [nodes[i][1] - nodes[i][0] for i in t]
        if a == c:
            return math.comb(n[0] + 2, 3)
        if a == b:
            return math.comb(n[0] + 1, 2) * n[2]
        if b == c:
            return n[0] * math.comb(n[1] + 1, 2)
        return math.prod(n)

    def children(t):
        choices = [i for i in t if nodes[i][2] >= 0]
        if not choices:
            return None
        chosen = max(choices, key=lambda i: nodes[i][1] - nodes[i][0])
        count = t.count(chosen)
        rest = [i for i in t if i != chosen]
        left, right = nodes[chosen][2:4]
        result = [tuple(sorted(rest + [left] * (count - k) + [right] * k)) for k in range(count + 1)]
        assert len(result) == len(set(result)) and sum(map(cardinality, result)) == cardinality(t)
        return result
    frontier = [(0, 0, 0)] if rows and alive((0, 0, 0)) else []
    pruned_regions = 0
    steps = 0
    total_triples = math.comb(len(rows) + 2, 3)
    pruned_triples = 0 if frontier else total_triples
    while frontier and len(frontier) < 8192:
        changed = False
        next_frontier = []
        for t in frontier:
            kids = children(t)
            if kids is None:
                next_frontier.append(t)
                continue
            changed = True
            steps += 1
            for q in kids:
                if alive(q):
                    next_frontier.append(q)
                else:
                    pruned_regions += 1
                    pruned_triples += cardinality(q)
        frontier = next_frontier
        if not changed:
            break
    raw = (folder / 'exceptions.bin.frontier').read_bytes()
    n, = struct.unpack_from('<I', raw)
    assert len(raw) == 4 + 12 * n
    actual = list(struct.iter_unpack('<iii', raw[4:]))
    assert actual == frontier
    tasks = json.loads((folder / 'exceptions.bin.tasks.json').read_bytes())
    native = json.loads((folder / 'exceptions.bin.json').read_bytes())
    assert tasks['start_task'] == 0 and tasks['next_task'] == tasks['total_tasks'] == n and (native['status'] == 'COMPLETE')
    survived = sum(map(cardinality, frontier))
    assert survived + pruned_triples == total_triples
    return dict(status='COMPLETE_FRONTIER_INDEPENDENTLY_VERIFIED', inputs=len(rows), nodes=len(nodes), frontier_tasks=n, covered_unordered_triples=survived, pruned_unordered_triples=pruned_triples, total_unordered_triples=total_triples, split_count=steps, necessary_bound_pruned_regions=pruned_regions, all_completed=True)
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument('directory', type=Path)
        a = p.parse_args()
        r = verify(a.directory)
        (a.directory / 'frontier_audit.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
        print(json.dumps(r))
    except Exception as error:
        _fail(error)
