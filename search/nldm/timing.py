"""Pin-load accumulation and rise/fall NLDM table propagation, in ps/fF."""
import argparse
import bisect
import hashlib
import json
import math
import re
from pathlib import Path
CELL_NAMES = ['INV', 'BUF', 'AND2', 'NAND2', 'OR2', 'NOR2', 'XOR2', 'XNOR2', 'AND3', 'NAND3', 'OR3', 'NOR3', 'AOI21', 'OAI21', 'MUX2', 'AND4', 'NAND4', 'OR4', 'NOR4', 'AOI22', 'OAI22']
KINDS = ('cell_rise', 'cell_fall', 'rise_transition', 'fall_transition')
NUM = '[-+]?\\d*\\.?\\d+(?:[eE][-+]?\\d+)?'

def groups(text, name):
    pattern = '\\b' + name + '\\s*\\(([^)]*)\\)\\s*\\{'
    for m in re.finditer(pattern, text):
        pos, depth = (m.end(), 1)
        end = pos
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        yield (m[1].strip().strip('"'), text[pos:end - 1])

def attr(text, name, default=None):
    m = re.search('\\b' + name + '\\s*:\\s*([^;]+);', text)
    return m[1].strip().strip('"') if m else default

class Table:

    def __init__(self, x, y, z):
        self.x, self.y, self.z = (x, y, z)
        self.planes = None
        assert len(x) >= 2 and len(y) >= 2 and (len(z) == len(x) * len(y))
        assert all((b > a for a, b in zip(x, x[1:])))
        assert all((b > a for a, b in zip(y, y[1:])))

    def exact(self, s, c):
        x, y, z = (self.x, self.y, self.z)
        i = max(0, min(len(x) - 2, bisect.bisect_right(x, s) - 1))
        j = max(0, min(len(y) - 2, bisect.bisect_right(y, c) - 1))
        u, v = ((s - x[i]) / (x[i + 1] - x[i]), (c - y[j]) / (y[j + 1] - y[j]))
        k, n = (i * len(y) + j, len(y))
        return (1 - u) * ((1 - v) * z[k] + v * z[k + 1]) + u * ((1 - v) * z[k + n] + v * z[k + n + 1])

    def prepare(self, bins=8, smax=200.0, cmax=50.0):
        if bins < 1 or smax <= 0 or cmax <= 0:
            raise ValueError('Positive bins and domain limits required')
        self.bins, self.smax, self.cmax = (bins, smax, cmax)
        self.si, self.ci = (bins / smax, bins / cmax)
        self.planes = []
        for i in range(bins):
            for j in range(bins):
                s0, s1 = (i / self.si, (i + 1) / self.si)
                c0, c1 = (j / self.ci, (j + 1) / self.ci)
                xs = [s0] + [v for v in self.x if s0 < v < s1] + [s1]
                ys = [c0] + [v for v in self.y if c0 < v < c1] + [c1]
                f00, f01 = (self.exact(s0, c0), self.exact(s0, c1))
                f10, f11 = (self.exact(s1, c0), self.exact(s1, c1))
                b = (f10 + f11 - f00 - f01) / (2 * (s1 - s0))
                r = (f01 + f11 - f00 - f10) / (2 * (c1 - c0))
                a = (f00 + f01 + f10 + f11) / 4 - b * (s0 + s1) / 2 - r * (c0 + c1) / 2
                residuals = [self.exact(s, c) - a - b * s - r * c for s in xs for c in ys]
                shift = (max(residuals) + min(residuals)) / 2
                a += shift
                error = (max(residuals) - min(residuals)) / 2 + 1e-10
                self.planes.append((a, b, r, error))
        xs = [0.0] + [v for v in self.x if 0 < v < smax] + [smax]
        ys = [0.0] + [v for v in self.y if 0 < v < cmax] + [cmax]
        self.lipschitz = max((abs((self.exact(b, c) - self.exact(a, c)) / (b - a)) for a, b in zip(xs, xs[1:]) for c in ys))

    def approx(self, s, c):
        if not (0 <= s <= self.smax and 0 <= c <= self.cmax):
            return (self.exact(s, c), 0.0, True)
        i, j = (min(self.bins - 1, int(s * self.si)), min(self.bins - 1, int(c * self.ci)))
        a, b, r, e = self.planes[i * self.bins + j]
        return (a + b * s + r * c, e, False)

    def uncertainty(self, s, c, incoming_error, value, residual):
        lo, hi = (max(0.0, s - incoming_error), s + incoming_error)
        if 0 <= lo <= hi <= self.smax and 0 <= c <= self.cmax:
            return residual + self.lipschitz * incoming_error + 1e-10
        points = [lo, hi] + [x for x in self.x if lo < x < hi]
        return max((abs(self.exact(x, c) - value) for x in points)) + 1e-10

def prepare(library, bins=16):
    for cell in library.values():
        for arc in cell['arcs']:
            for table in arc['tables']:
                if table.planes is None or table.bins != bins:
                    table.prepare(bins)

def compile_graph(spec, library):
    """Inputs are 0..n-1, topologically ordered gate outputs are n..n+g-1."""
    n = spec['n_inputs']
    if not isinstance(n, int) or n < 1 or (not spec['outputs']):
        raise ValueError('Require inputs and at least one output')
    count = n + len(spec['gates'])
    loads = [[0.0, 0.0] for _ in range(count)]
    gates = []
    for k, g in enumerate(spec['gates']):
        cell = library[g['cell']]
        if set(g['pins']) != set(cell['pins']):
            raise ValueError('Physical pin names must match library')
        for pin, src in g['pins'].items():
            if not isinstance(src, int) or not 0 <= src < n + k:
                raise ValueError('Invalid source, constant, cycle, or non-topological graph')
            for q in (0, 1):
                loads[src][q] += cell['pins'][pin][q]
        gates.append([(g['pins'][a['pin']], a['sense'], a['tables']) for a in cell['arcs']])
    for out in spec['outputs']:
        src = out['node'] if isinstance(out, dict) else out
        cap = out.get('load_ff', spec.get('output_load_ff', 5.0)) if isinstance(out, dict) else spec.get('output_load_ff', 5.0)
        if not isinstance(src, int) or not 0 <= src < count or cap < 0:
            raise ValueError('Invalid output or load')
        for q in (0, 1):
            loads[src][q] += cap
    outputs = [o['node'] if isinstance(o, dict) else o for o in spec['outputs']]
    return (n, loads, gates, outputs)

def evaluate_python(graph, library, s0=20.0, mode='exact', certify=False, boundary=None):
    """Optional boundary: one {arrival_ps:[r,f],slew_ps:[r,f]} per input.

    Boundary states must already include the actual surrounding load effects.
    Otherwise each primary input gets the paper's INV_X1 reference driver.
    """
    if mode not in ('exact', 'affine', 'fixed') or s0 < 0:
        raise ValueError('Invalid mode or slew')
    n, loads, gates, outputs = graph
    arrival, slew, ae, se = ([], [], [], [])
    fallbacks = queries = 0

    def query(tab, s, c, e=0.0):
        nonlocal fallbacks, queries
        queries += 1
        if mode == 'exact':
            return (tab.exact(s, c), 0.0)
        if mode == 'fixed':
            return (tab.exact(20.0, 5.0), 0.0)
        value, res, fallback = tab.approx(s, c)
        fallbacks += fallback
        return (value, tab.uncertainty(s, c, e, value, res) if certify else 0.0)
    drv = library['INV_X1']['arcs'][0]['tables']
    if boundary is not None and len(boundary) != n:
        raise ValueError('Boundary count mismatch')
    for i in range(n):
        if boundary is None:
            arrival.append([drv[q].exact(s0, loads[i][q]) - drv[q].exact(s0, 0.0) for q in (0, 1)])
            slew.append([max(0.0, drv[q + 2].exact(s0, loads[i][q])) for q in (0, 1)])
        else:
            arrival.append(list(boundary[i]['arrival_ps']))
            slew.append(list(boundary[i]['slew_ps']))
            if len(arrival[-1]) != 2 or len(slew[-1]) != 2 or min(slew[-1]) < 0:
                raise ValueError('Invalid boundary state')
        ae.append([0.0, 0.0])
        se.append([0.0, 0.0])
    for v, arcs in enumerate(gates, n):
        av, sv, ev, fv = ([], [], [], [])
        for q in (0, 1):
            ac, sc, ec, fc = ([], [], [], [])
            for src, sense, tables in arcs:
                polarities = (q,) if sense == 'positive_unate' else (1 - q,) if sense == 'negative_unate' else (0, 1)
                for p in polarities:
                    d, de = query(tables[q], slew[src][p], loads[v][q], se[src][p])
                    t, te = query(tables[q + 2], slew[src][p], loads[v][q], se[src][p])
                    ac.append(arrival[src][p] + d)
                    sc.append(max(0.0, t))
                    ec.append(ae[src][p] + de)
                    fc.append(te)
            av.append(max(ac))
            sv.append(max(sc))
            ev.append(max(ec))
            fv.append(max(fc))
        arrival.append(av)
        slew.append(sv)
        ae.append(ev)
        se.append(fv)
    delay = max((arrival[o][q] for o in outputs for q in (0, 1)))
    error = max((ae[o][q] for o in outputs for q in (0, 1)))
    return dict(delay_ps=delay, error_bound_ps=error if certify else None, fallback_queries=fallbacks, table_queries=queries, arrivals_ps=arrival, slews_ps=slew)
native_engine = None

def evaluate(graph, library, s0=20.0, mode='exact', certify=False, boundary=None):
    if native_engine is not None and native_engine.library is library and (mode == 'exact') and (boundary is None) and (not certify):
        return native_engine.evaluate(graph, s0)
    return evaluate_python(graph, library, s0, mode, certify, boundary)


class NLDM:
    def __init__(self, library, slew_ps=20.):
        self.library, self.slew_ps = library, slew_ps

    def __call__(self, spec, background_ff=0.):
        graph = compile_graph(spec, self.library)
        if background_ff:
            for load in graph[1][:graph[0]]:
                load[0] += background_ff
                load[1] += background_ff
        result = evaluate_python(graph, self.library, self.slew_ps)
        result['outputs_ps'] = [max(result['arrivals_ps'][o]) for o in graph[3]]
        return result
