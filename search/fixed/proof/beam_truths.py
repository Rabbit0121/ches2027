"""Truth-table expansion for one fixed structure.

This cache is keyed by the exact typed structure, not by a delay budget.
Intermediate AND/OR compositions are deduplicated before further expansion.
We retain actual variable labels and paid leaf polarities; input/output
complement equivalence from the paper is not assumed free in this model.
"""
from .runtime import run as _run, fail as _fail
import argparse, json, time
from pathlib import Path
from .model import gate, expression
from .structures import freeze, metrics, input_truths
from .model import S
Y = sum(((v >> 2) & 1) << x for x, v in enumerate(S))

class ExpansionLimit(Exception):
    pass

class Engine:

    def __init__(self, nvars=6, max_functions=0):
        self.nvars = nvars
        self.mask = (1 << (1 << nvars)) - 1
        self.max_functions = max_functions
        self.cache = {}
        self.compositions = 0
        self.duplicates = 0

    def insert(self, table, truth, witness):
        if truth in table:
            self.duplicates += 1
            return
        if self.max_functions and len(table) >= self.max_functions:
            raise ExpansionLimit('Explicit per-table function limit reached')
        table[truth] = witness

    def join(self, left, right, op):
        result = {}
        for a, wa in left.items():
            for b, wb in right.items():
                self.compositions += 1
                v = a & b if op == 'AND' else a | b if op == 'OR' else a ^ b
                self.insert(result, v, wa + wb)
        return result

    def combine(self, tables, op):
        result = {f: (e,) for f, e in tables[0].items()}
        for table in tables[1:]:
            result = self.join(result, {f: (e,) for f, e in table.items()}, op)
        return result

    def expand(self, s):
        if s in self.cache:
            return self.cache[s]
        g = s[0]
        out = {}
        if len(s) == 1:
            for i, f in enumerate(input_truths(self.nvars)):
                out[gate(g, [f], self.mask)] = [g, f'x{i}']
        else:
            tables = [self.expand(c) for c in s[1:]]
            if g in ('BUF', 'INV'):
                for f, e in tables[0].items():
                    out[gate(g, [f], self.mask)] = [g, e]
            elif g == 'MUX2':
                for select, es in tables[2].items():
                    low = {}
                    high = {}
                    for f, e in tables[0].items():
                        self.insert(low, f & (~select & self.mask), e)
                    for f, e in tables[1].items():
                        self.insert(high, f & select, e)
                    for a, ea in low.items():
                        for b, eb in high.items():
                            self.compositions += 1
                            self.insert(out, a | b, [g, ea, eb, es])
            else:
                if g in ('AOI21', 'OAI21', 'AOI22', 'OAI22'):
                    inside = 'AND' if g.startswith('AOI') else 'OR'
                    outside = 'OR' if inside == 'AND' else 'AND'
                    left = self.combine(tables[:2], inside)
                    right = {f: (e,) for f, e in tables[2].items()} if g.endswith('21') else self.combine(tables[2:], inside)
                    partial = self.join(left, right, outside)
                    invert = True
                else:
                    op = 'XOR' if g in ('XOR2', 'XNOR2') else 'AND' if g.startswith(('AND', 'NAND')) else 'OR'
                    partial = self.combine(tables, op)
                    invert = g.startswith(('NAND', 'NOR')) or g == 'XNOR2'
                for f, args in partial.items():
                    self.insert(out, f ^ self.mask if invert else f, [g, *args])
        self.cache[s] = out
        return out

    def match(self, s, target):
        """Test one fixed target without building the root's full truth set."""
        g = s[0]
        if len(s) == 1:
            return self.expand(s).get(target)
        tables = [self.expand(c) for c in s[1:]]
        if g in ('INV', 'BUF'):
            needed = target ^ self.mask if g == 'INV' else target
            return [g, tables[0][needed]] if needed in tables[0] else None
        if g in ('XOR2', 'XNOR2'):
            needed = target ^ self.mask if g == 'XNOR2' else target
            for f, e in tables[0].items():
                other = needed ^ f
                if other in tables[1]:
                    return [g, e, tables[1][other]]
            return None
        if g == 'MUX2':
            for select, es in tables[2].items():
                low = next((e for f, e in tables[0].items() if f & ~select == target & ~select), None)
                if low is None:
                    continue
                high = next((e for f, e in tables[1].items() if f & select == target & select), None)
                if high is not None:
                    return [g, low, high, es]
            return None
        invert = g.startswith(('NAND', 'NOR', 'AOI', 'OAI'))
        needed = target ^ self.mask if invert else target
        if g in ('AOI21', 'OAI21', 'AOI22', 'OAI22'):
            inner = 'AND' if g.startswith('AOI') else 'OR'
            outer = 'OR' if inner == 'AND' else 'AND'
            left = self.combine(tables[:2], inner)
            right = {f: (e,) for f, e in tables[2].items()} if g.endswith('21') else self.combine(tables[2:], inner)
        else:
            outer = 'AND' if g.startswith(('AND', 'NAND')) else 'OR'

            def eligible(f):
                return f & needed == needed if outer == 'AND' else f | needed == needed
            tables = [{f: e for f, e in table.items() if eligible(f)} for table in tables]
            if any((not table for table in tables)):
                return None
            left = self.combine(tables[:-1], outer)
            right = {f: (e,) for f, e in tables[-1].items()}
        if outer == 'AND':
            left = {f: e for f, e in left.items() if f & needed == needed}
            right = {f: e for f, e in right.items() if f & needed == needed}
        else:
            left = {f: e for f, e in left.items() if f | needed == needed}
            right = {f: e for f, e in right.items() if f | needed == needed}
        for a, ea in left.items():
            for b, eb in right.items():
                self.compositions += 1
                if (a & b if outer == 'AND' else a | b) == needed:
                    return [g, *ea, *eb]
        return None

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--shape-file', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--max-functions', type=int, default=0)
    p.add_argument('--expand-all', action='store_true', help='Optional diagnostic full root truth set; default checks only Y2')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    shape = freeze(json.loads(a.shape_file.read_bytes()))
    engine = Engine(max_functions=a.max_functions)
    start = time.time()
    r = dict(global_lower_bound_proved=False, shape=shape, delay_fs=metrics(shape)[0])
    try:
        if a.expand_all:
            table = engine.expand(shape)
            witness = table.get(Y)
            r.update(status='FIXED_STRUCTURE_EXPANSION_COMPLETE', functions=len(table), contains_y2=Y in table)
        else:
            witness = engine.match(shape, Y)
            r.update(status='FIXED_STRUCTURE_Y2_CHECK_COMPLETE', contains_y2=witness is not None, target_y2=Y)
        if witness is not None:
            truth, delay = expression(witness)
            assert truth == Y and delay == r['delay_fs']
            r['witness'] = witness
    except ExpansionLimit as e:
        r.update(status='PARTIAL', reason=str(e))
    r.update(compositions=engine.compositions, duplicate_compositions=engine.duplicates, cached_structures=len(engine.cache), seconds=time.time() - start)
    (a.output / 'status.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    print(json.dumps(r, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
