"""Independent scalar evaluation: no search metadata or digest is trusted."""
from collections import Counter
from ...core.model import ARITY

def scalar(g,a):
    if g == 'BUF': return a[0]
    if g == 'INV': return 1-a[0]
    if g.startswith('NAND'): return int(not all(a))
    if g.startswith('AND'): return int(all(a))
    if g.startswith('NOR'): return int(not any(a))
    if g.startswith('OR'): return int(any(a))
    if g == 'XOR2': return int(a[0] != a[1])
    if g == 'XNOR2': return int(a[0] == a[1])
    if g == 'MUX2': return a[1] if a[2] else a[0]
    if g == 'AOI21': return int(not ((a[0] and a[1]) or a[2]))
    if g == 'OAI21': return int(not ((a[0] or a[1]) and a[2]))
    if g == 'AOI22': return int(not ((a[0] and a[1]) or (a[2] and a[3])))
    if g == 'OAI22': return int(not ((a[0] or a[1]) and (a[2] or a[3])))
    raise ValueError(g)

def audit(p, circuit, partial=False):
    rows = circuit['gates']; outputs = circuit['outputs']
    if not partial and set(outputs) != {f'y{j}' for j in range(p.m)}: raise ValueError('Missing outputs')
    times = {x:0 for x in p.inputs}; depths = dict(times); by = {}
    for row in rows:
        name,g,args = row['out'],row['type'],row['in']
        if name in times or g not in p.costs or len(args) != ARITY[g]: raise ValueError('Invalid node')
        if any(a not in times for a in args): raise ValueError('Non-topological/cyclic netlist')
        if any(a in p.inputs for a in args) and g not in ('BUF','INV'): raise ValueError('Unpaid input')
        times[name] = p.costs[g]+max(times[a] for a in args)
        depths[name] = 1+max(depths[a] for a in args); by[name] = row
        if 'arrival_fs' in row and row['arrival_fs'] != times[name]: raise ValueError('False timing metadata')
    for y,node in outputs.items():
        if y not in {f'y{j}' for j in range(p.m)} or node not in by: raise ValueError('Illegal/unpaid output')
    for x in range(1 << p.n):
        values = {f'x{i}':(x>>i)&1 for i in range(p.n)}
        for r in rows: values[r['out']] = scalar(r['type'],[values[a] for a in r['in']])
        for y,node in outputs.items():
            if values[node] != ((p.sbox[x] >> int(y[1:])) & 1): raise ValueError(f'Wrong {y} on input {x}')
    ts = {y:times[n] for y,n in outputs.items()}
    worst = max(ts,key=ts.get) if ts else None; path = []
    n = outputs[worst] if worst else None
    while n in by:
        row=by[n]; path.append(dict(node=n,gate=row['type'],arrival_fs=times[n]))
        n=max(row['in'],key=times.get)
    if n is not None: path.append(dict(node=n,arrival_fs=0))
    delta = max(max(Counter(p.sbox[x]^p.sbox[x^a] for x in range(1<<p.n)).values()) for a in range(1,1<<p.n))
    return dict(status='PASS',all_outputs_found=len(outputs)==p.m,checked_inputs=1<<p.n,
        outputs_fs=ts,worst_fs=max(ts.values(),default=None),gate_count=len(rows),
        boundary_BUF_INV=True,critical_path=path[::-1],differential_uniformity=delta,
        permutation=p.n==p.m and len(set(p.sbox))==len(p.sbox),
        outputs_depth={y:depths[n] for y,n in outputs.items()})
