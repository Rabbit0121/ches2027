"""Emit a finite-cover failure DAG, then verify every branch independently.

This certifies the finite set-cover query, NOT the completeness of its input
basis. That obligation belongs to the complete child-root generator.
"""
from ...runtime import run as _run, fail as _fail
import argparse, json, struct, time
from pathlib import Path

def emit(basis_path, out, k):
    data = json.loads(basis_path.read_bytes())
    goal = data['target']
    values = data['zero_masks']
    assert goal and values and all((0 <= v <= 2 ** 64 - 1 and (not v & ~goal) for v in values))
    assert len(set(values)) == len(values)
    posts = {b: sum((1 << i for i, v in enumerate(values) if v >> b & 1)) for b in range(64) if goal >> b & 1}
    order = sorted(posts, key=lambda b: posts[b].bit_count())
    full = (1 << len(values)) - 1
    failed = set()

    def visit(missing, left):
        if not missing:
            return True
        if left == 0:
            return False
        key = (missing, left)
        if key in failed:
            return False
        if left == 1:
            ids = full
            for b in order:
                if missing >> b & 1:
                    ids &= posts[b]
            if ids:
                return True
        else:
            b = next((b for b in order if missing >> b & 1))
            ids = posts[b]
            seen = set()
            while ids:
                bit = ids & -ids
                ids ^= bit
                child = missing & ~values[bit.bit_length() - 1]
                if child not in seen:
                    seen.add(child)
                    if visit(child, left - 1):
                        return True
        failed.add(key)
        return False
    assert not visit(goal, k), 'A cover exists; no failure certificate can be issued'
    with (out / 'failure_dag.bin').open('wb') as f:
        f.write(struct.pack('<I', len(failed)))
        for missing, left in sorted(failed):
            f.write(struct.pack('<QB', missing, left))
    (out / 'basis.json').write_text(json.dumps(data), encoding='utf-8')
    (out / 'claim.json').write_text(json.dumps(dict(target=goal, slots=k)), encoding='utf-8')

def verify(out):
    data = json.loads((out / 'basis.json').read_bytes())
    claim = json.loads((out / 'claim.json').read_bytes())
    goal = claim['target']
    values = data['zero_masks']
    k = claim['slots']
    assert data['target'] == goal
    assert goal and 1 <= k <= 4 and all((v >= 0 and (not v & ~goal) for v in values))
    raw = (out / 'failure_dag.bin').read_bytes()
    n, = struct.unpack_from('<I', raw)
    assert len(raw) == 4 + 9 * n
    proof = set(struct.iter_unpack('<QB', raw[4:]))
    assert len(proof) == n and (goal, k) in proof
    posts = {b: 0 for b in range(64) if goal >> b & 1}
    for i, value in enumerate(values):
        for b in posts:
            if value >> b & 1:
                posts[b] |= 1 << i
    order = sorted(posts, key=lambda b: posts[b].bit_count())
    full = (1 << len(values)) - 1
    edges = 0
    for missing, left in proof:
        assert missing and (not missing & ~goal) and (1 <= left <= k)
        if left == 1:
            candidates = full
            remaining = missing
            while remaining and candidates:
                bit = remaining & -remaining
                remaining ^= bit
                candidates &= posts[bit.bit_length() - 1]
            assert not candidates
        else:
            b = next((b for b in order if missing >> b & 1))
            for v in values:
                if v >> b & 1:
                    assert (missing & ~v, left - 1) in proof
                    edges += 1
    return dict(status='FINITE_COVER_FAILURE_INDEPENDENTLY_VERIFIED', basis_size=len(values), failure_states=n, checked_edges=edges, scope='Finite cover only; input-domain completeness is a separate obligation')
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument('--basis', type=Path)
        p.add_argument('--output', required=True, type=Path)
        p.add_argument('--slots', type=int, default=4)
        p.add_argument('--verify-only', action='store_true')
        a = p.parse_args()
        start = time.time()
        if not a.verify_only:
            assert a.basis is not None
            a.output.mkdir(parents=True, exist_ok=False)
            emit(a.basis, a.output, a.slots)
        report = verify(a.output)
        report['seconds'] = time.time() - start
        (a.output / 'certificate.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    except Exception as error:
        _fail(error)
