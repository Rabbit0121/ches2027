"""Problem data, legal pins and explicit paid-input circuit semantics."""
from dataclasses import dataclass
from itertools import combinations_with_replacement, product
import json

DEFAULT_COSTS = dict(INV=22048, BUF=33557, NAND2=27886, NOR2=40650,
    AND2=40171, OR2=56414, XOR2=73019, XNOR2=57604, NAND3=34767,
    OAI21=32651, AOI21=51619, NOR3=61543, AND3=51869, OR3=85840,
    MUX2=75175, OAI22=54596, AOI22=57255, NAND4=44487, NOR4=91313,
    AND4=65492, OR4=118592)
ARITY = {g: 1 if g in ('INV','BUF') else 3 if g in ('AOI21','OAI21','MUX2')
         else 4 if g in ('AOI22','OAI22') else int(g[-1]) for g in DEFAULT_COSTS}

def gate(g, a, mask):
    if g == 'BUF': v = a[0]
    elif g == 'INV': v = ~a[0]
    elif g.startswith(('NAND','AND')):
        v = mask
        for x in a: v &= x
        if g.startswith('NAND'): v = ~v
    elif g.startswith(('NOR','OR')):
        v = 0
        for x in a: v |= x
        if g.startswith('NOR'): v = ~v
    elif g == 'XOR2': v = a[0] ^ a[1]
    elif g == 'XNOR2': v = ~(a[0] ^ a[1])
    elif g == 'OAI21': v = ~((a[0] | a[1]) & a[2])
    elif g == 'AOI21': v = ~((a[0] & a[1]) | a[2])
    elif g == 'OAI22': v = ~((a[0] | a[1]) & (a[2] | a[3]))
    elif g == 'AOI22': v = ~((a[0] & a[1]) | (a[2] & a[3]))
    elif g == 'MUX2': v = (a[0] & ~a[2]) | (a[1] & a[2])
    else: raise ValueError(g)
    return v & mask

def pins(g, count):
    if g == 'MUX2': yield from product(range(count), repeat=3)
    elif g in ('OAI21','AOI21'):
        for a,b in combinations_with_replacement(range(count),2):
            for c in range(count): yield a,b,c
    elif g in ('OAI22','AOI22'):
        pairs = list(combinations_with_replacement(range(count),2))
        for p,q in combinations_with_replacement(pairs,2): yield *p,*q
    else: yield from combinations_with_replacement(range(count), ARITY[g])

@dataclass
class Problem:
    name: str
    n: int
    m: int
    sbox: list
    costs: dict

    def __post_init__(self):
        if type(self.n) is not int or not 1 <= self.n <= 10:
            raise ValueError('n_inputs must be an integer in 1..10')
        if type(self.m) is not int or not 1 <= self.m <= 16:
            raise ValueError('n_outputs must be an integer in 1..16')
        if len(self.sbox) != 1 << self.n or any(type(v) is not int or not 0 <= v < 1 << self.m for v in self.sbox):
            raise ValueError('Invalid truth table length or output value')
        if not {'INV','BUF'} <= self.costs.keys() or any(g not in ARITY or type(c) is not int or c <= 0 for g,c in self.costs.items()):
            raise ValueError('Positive integer gate costs and paid INV/BUF are required')
        self.mask = (1 << (1 << self.n)) - 1
        self.inputs = {f'x{i}': sum(((x >> i) & 1) << x for x in range(1 << self.n)) for i in range(self.n)}
        self.targets = [sum(((v >> j) & 1) << x for x,v in enumerate(self.sbox)) for j in range(self.m)]

    @classmethod
    def load(cls, path):
        d = json.loads(path.read_text(encoding='utf-8-sig'))
        return cls(d.get('name', path.stem), d['n_inputs'], d['n_outputs'], d['sbox'], d.get('gate_costs_fs', dict(DEFAULT_COSTS)))

    def data(self):
        return dict(name=self.name,n_inputs=self.n,n_outputs=self.m,sbox=self.sbox,gate_costs_fs=self.costs)

    def expression(self, e, parent=None):
        if isinstance(e, str):
            if e not in self.inputs or parent not in ('BUF','INV'): raise ValueError('Unpaid input edge')
            return self.inputs[e], 0
        g,*args = e
        if g not in self.costs or len(args) != ARITY[g]: raise ValueError('Illegal gate')
        children = [self.expression(a,g) for a in args]
        return gate(g,[c[0] for c in children],self.mask), self.costs[g]+max(c[1] for c in children)

def emit(expressions):
    rows, memo = [], {}
    def visit(e):
        if isinstance(e,str): return e
        args = tuple(visit(a) for a in e[1:])
        key = (e[0], args)
        if key not in memo:
            name = f'n{len(rows)}'
            memo[key] = name
            rows.append(dict(out=name,type=e[0],**{'in':list(args)}))
        return memo[key]
    outputs = {f'y{j}':visit(e) for j,e in sorted(expressions.items())}
    return dict(gates=rows,outputs=outputs)
