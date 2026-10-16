"""Fixed APN6 target and paid-input gate semantics."""
from .runtime import run as _run, fail as _fail
import json, collections, time
if not __debug__:
    raise SystemExit('Do not disable assertions')
M = (1 << 64) - 1
D = dict(INV=22048, BUF=33557, NAND2=27886, NOR2=40650, AND2=40171, OR2=56414, XOR2=73019, XNOR2=57604, NAND3=34767, OAI21=32651, AOI21=51619, NOR3=61543, AND3=51869, OR3=85840, MUX2=75175, OAI22=54596, AOI22=57255, NAND4=44487, NOR4=91313, AND4=65492, OR4=118592)
ARITY = {g: 1 if g in ('INV', 'BUF') else 3 if g in ('OAI21', 'AOI21', 'MUX2') else 4 if g in ('OAI22', 'AOI22') else int(g[-1]) for g in D}
S = [0, 54, 48, 13, 15, 18, 53, 35, 25, 63, 45, 52, 3, 20, 41, 33, 59, 36, 2, 34, 10, 8, 57, 37, 60, 19, 42, 14, 50, 26, 58, 24, 39, 27, 21, 17, 16, 29, 1, 62, 47, 40, 51, 56, 7, 43, 44, 38, 31, 11, 4, 28, 61, 46, 5, 49, 9, 6, 23, 32, 30, 12, 55, 22]
PI = {f'x{i}': sum(((x >> i & 1) << x for x in range(64))) for i in range(6)}

def gate(g, a, mask=M):
    if g == 'BUF':
        v = a[0]
    elif g == 'INV':
        v = ~a[0]
    elif g.startswith(('NAND', 'AND')):
        v = mask
        for z in a:
            v &= z
        if g.startswith('NAND'):
            v = ~v
    elif g.startswith(('NOR', 'OR')):
        v = 0
        for z in a:
            v |= z
        if g.startswith('NOR'):
            v = ~v
    elif g == 'XOR2':
        v = a[0] ^ a[1]
    elif g == 'XNOR2':
        v = ~(a[0] ^ a[1])
    elif g == 'OAI21':
        v = ~((a[0] | a[1]) & a[2])
    elif g == 'AOI21':
        v = ~(a[0] & a[1] | a[2])
    elif g == 'OAI22':
        v = ~((a[0] | a[1]) & (a[2] | a[3]))
    elif g == 'AOI22':
        v = ~(a[0] & a[1] | a[2] & a[3])
    elif g == 'MUX2':
        v = a[0] & ~a[2] | a[1] & a[2]
    else:
        raise ValueError(g)
    return v & mask

def expression(e, parent=None):
    if isinstance(e, str):
        assert parent in ('BUF', 'INV') and e in PI
        return (PI[e], 0)
    g = e[0]
    assert len(e) == ARITY[g] + 1
    parts = [expression(a, g) for a in e[1:]]
    return (gate(g, [p[0] for p in parts]), max((p[1] for p in parts)) + D[g])

def maximal(pool):
    kept = {}
    posts = [0] * 64
    for z in sorted(pool, key=lambda z: (-z.bit_count(), z)):
        ids = (1 << len(kept)) - 1
        v = z
        while v and ids:
            bit = v & -v
            v ^= bit
            ids &= posts[bit.bit_length() - 1]
        if ids:
            continue
        i = len(kept)
        kept[z] = pool[z]
        v = z
        while v:
            bit = v & -v
            v ^= bit
            posts[bit.bit_length() - 1] |= 1 << i
    return kept

def cover4(pool, Y):
    zs = list(pool)
    full = (1 << len(zs)) - 1
    posts = {b: 0 for b in range(64) if Y >> b & 1}
    for i, z in enumerate(zs):
        for b in posts:
            if z >> b & 1:
                posts[b] |= 1 << i
    order = sorted(posts, key=lambda b: posts[b].bit_count())
    failed = set()
    start = time.perf_counter()
    states = 0

    def visit(missing, k):
        nonlocal states
        if not missing:
            return []
        key = (missing, k)
        if key in failed:
            return None
        states += 1
        if time.perf_counter() - start > 120:
            raise TimeoutError('UNKNOWN, never a proof of nonexistence')
        if k == 1:
            ids = full
            for b in order:
                if missing >> b & 1:
                    ids &= posts[b]
                if not ids:
                    break
            if ids:
                return [(ids & -ids).bit_length() - 1]
        else:
            b = next((b for b in order if missing >> b & 1))
            ids = posts[b]
            seen = set()
            while ids:
                low = ids & -ids
                ids ^= low
                i = low.bit_length() - 1
                left = missing & ~zs[i]
                if left in seen:
                    continue
                seen.add(left)
                r = visit(left, k - 1)
                if r is not None:
                    return [i] + r
        failed.add(key)
        return None
    ids = visit(Y, 4)
    if ids is None:
        return (None, states)
    ids += (4 - len(ids)) * [ids[0]]
    return ([pool[zs[i]] for i in ids], states)

def emit(es):
    gates = []
    memo = {}

    def node(e):
        if isinstance(e, str):
            return e
        key = json.dumps(e, separators=(',', ':'))
        if key not in memo:
            ins = [node(a) for a in e[1:]]
            name = f'method_{len(gates)}'
            gates.append({'id': name, 'out': name, 'type': e[0], 'in': ins})
            memo[key] = name
        return memo[key]
    return {'name': 'reproduced_paid_cover', 'n_inputs': 6, 'n_outputs': 6, 'target': {'mode': 'fixed_s0_6bit'}, 'gates': gates, 'outputs': {y: node(e) for y, e in es.items()}}

def audit(spec):
    nets = dict(PI)
    ts = {n: 0 for n in PI}
    by = {}
    scalar = {n: [x >> int(n[1]) & 1 for x in range(64)] for n in PI}
    for g in spec['gates']:
        typ = g['type']
        ins = g['in']
        n = g['out']
        assert len(ins) == ARITY[typ] and n not in nets
        assert all((i not in PI or typ in ('BUF', 'INV') for i in ins))
        nets[n] = gate(typ, [nets[i] for i in ins])
        ts[n] = max((ts[i] for i in ins)) + D[typ]
        by[n] = g
        scalar[n] = [gate(typ, [scalar[i][x] for i in ins], 1) for x in range(64)]
    table = [sum((scalar[spec['outputs'][f'y{i}']][x] << i for i in range(6))) for x in range(64)]
    assert table == S
    for i in range(6):
        assert nets[spec['outputs'][f'y{i}']] == sum(((v >> i & 1) << x for x, v in enumerate(S)))
    delta = max((max(collections.Counter((table[x] ^ table[x ^ a] for x in range(64))).values()) for a in range(1, 64)))
    assert delta == 2 and len(set(table)) == 64
    times = {y: ts[n] for y, n in spec['outputs'].items()}
    y = max(times, key=times.get)
    n = spec['outputs'][y]
    path = []
    while n in by:
        g = by[n]
        path.append({'node': n, 'gate': g['type'], 'increment_fs': D[g['type']], 'arrival_fs': ts[n]})
        n = max(g['in'], key=ts.get)
    path.append({'node': n, 'arrival_fs': 0})
    path.reverse()
    return {'status': 'PASS', 'all64_fixed_S0': True, 'APN_delta': delta, 'boundary_BUF_INV': True, 'gate_count': len(by), 'gate_histogram': dict(collections.Counter((g['type'] for g in by.values()))), 'outputs_fs': times, 'worst_fs': max(times.values()), 'critical_output': y, 'critical_path': path}

def canonical_dag(spec):
    ids = {f'x{i}': f'x{i}' for i in range(6)}
    rows = []
    for i, g in enumerate(spec['gates']):
        rows.append([g['type'], [ids[n] for n in g['in']]])
        ids[g['out']] = i
    return (rows, {y: ids[n] for y, n in spec['outputs'].items()})
