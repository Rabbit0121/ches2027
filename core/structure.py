"""Physical, ordered gate structures using the original Boolean semantics."""
from dataclasses import dataclass
from itertools import permutations
from .model import Problem, ARITY, gate


class StructureLimit(RuntimeError):
    """A declared search resource has been reached; retain the incumbent."""


def physical_pins(g):
    if g in ('BUF', 'INV'):
        return ('A',)
    if g in ('AOI21', 'OAI21'):
        return ('B1', 'B2', 'A')
    if g in ('AOI22', 'OAI22'):
        return ('A1', 'A2', 'B1', 'B2')
    if g == 'MUX2':
        return ('A', 'B', 'S')
    return tuple(f'A{i+1}' for i in range(ARITY[g])) if g not in ('XOR2', 'XNOR2') else ('A', 'B')


@dataclass(frozen=True)
class Node:
    id: int
    kind: str
    args: tuple
    truth: int
    depth: int
    theoretical_fs: int


class Structures:
    """Intern physical identities, never merge by Boolean truth or timing score."""
    def __init__(self, problem):
        self.problem = problem
        self.nodes = []
        self.identities = {}
        self.max_nodes = None

    def truth(self, i):
        return self.problem.inputs[f'x{-i-1}'] if i < 0 else self.nodes[i].truth

    def make(self, kind, args):
        args = tuple(args)
        if kind not in self.problem.costs or len(args) != ARITY[kind]:
            raise ValueError('Disabled gate or incorrect arity')
        if any(i < 0 for i in args) and kind not in ('BUF', 'INV'):
            raise ValueError('Primary inputs require a paid BUF/INV')
        if any(not -self.problem.n <= i < len(self.nodes) for i in args):
            raise ValueError('Invalid child structure')
        key = kind, args
        if key not in self.identities:
            if self.max_nodes is not None and len(self.nodes) >= self.max_nodes:
                raise StructureLimit('generated structure limit reached')
            node = Node(len(self.nodes), kind, args,
                gate(kind, [self.truth(i) for i in args], self.problem.mask),
                1+max(0 if i < 0 else self.nodes[i].depth for i in args),
                self.problem.costs[kind]+max(0 if i < 0 else self.nodes[i].theoretical_fs for i in args))
            self.identities[key] = node.id
            self.nodes.append(node)
        return self.identities[key]

    def import_expression(self, e):
        if isinstance(e, str):
            return -int(e[1:])-1
        return self.make(e[0], [self.import_expression(a) for a in e[1:]])

    def expression(self, i):
        if i < 0:
            return f'x{-i-1}'
        n = self.nodes[i]
        return [n.kind, *[self.expression(a) for a in n.args]]

    def descendants(self, root):
        seen = set()
        def visit(i):
            if i < 0 or i in seen:
                return
            seen.add(i)
            for a in self.nodes[i].args:
                visit(a)
        visit(root)
        return seen

    def rewire(self,roots,old,replacement):
        memo={old:replacement}
        def visit(i):
            if i < 0:
                return i
            if i not in memo:
                n=self.nodes[i]
                args=tuple(visit(a) for a in n.args)
                memo[i]=i if args==n.args else self.make(n.kind,args)
            return memo[i]
        return [visit(i) for i in roots]

    def pin_variants(self,i):
        n=self.nodes[i]
        if n.kind in ('BUF','INV','MUX2'):
            return []
        if n.kind in ('AOI21','OAI21'):
            choices=[(n.args[1],n.args[0],n.args[2])]
        elif n.kind in ('AOI22','OAI22'):
            a,b,c,d=n.args
            choices=[(b,a,c,d),(a,b,d,c),(c,d,a,b),(d,c,a,b),(c,d,b,a),(b,a,d,c),(d,c,b,a)]
        else:
            choices=permutations(n.args)
        return [self.make(n.kind,args) for args in dict.fromkeys(choices) if args!=n.args]

    def graph(self, roots, output_load_ff=5., sharing=True):
        p = self.problem
        rows, memo, node_occurrences = [], {}, {}
        def visit(i):
            if i < 0:
                return -i-1
            if sharing and i in memo:
                return memo[i]
            node = self.nodes[i]
            args = [visit(a) for a in node.args]
            result = p.n+len(rows)
            rows.append(dict(cell=node.kind+'_X1', pins=dict(zip(physical_pins(node.kind), args))))
            memo[i] = result
            node_occurrences.setdefault(i, []).append(result)
            return result
        outputs = [visit(i) for i in roots]
        caps = [output_load_ff]*len(roots) if isinstance(output_load_ff, (int, float)) else output_load_ff
        if len(caps) != len(roots):
            raise ValueError('Output load count mismatch')
        return dict(n_inputs=p.n, gates=rows,
                    outputs=[dict(node=o, load_ff=float(c)) for o,c in zip(outputs,caps)]), node_occurrences

    def circuit(self, roots, sharing=True):
        spec, _ = self.graph(roots, sharing=sharing)
        p = self.problem
        def name(i):
            return f'x{i}' if i < p.n else f'n{i-p.n}'
        return dict(gates=[dict(out=f'n{j}',type=g['cell'][:-3],
                    **{'in':[name(g['pins'][pin]) for pin in physical_pins(g['cell'][:-3])]})
                    for j,g in enumerate(spec['gates'])],
                    outputs={f'y{j}': name(o['node']) for j,o in enumerate(spec['outputs'])})
