"""Common interface for local ranking and complete-circuit timing."""
from collections import OrderedDict
from types import SimpleNamespace
from . import nldm
from ..core.model import gate


def invert_pin(structures, kind, prefix, value, care):
    mask = structures.problem.mask
    args = [structures.truth(i) for i in prefix]
    zero = gate(kind, args + [0], mask)
    one = gate(kind, args + [mask], mask)
    delta = zero ^ one
    return (value ^ zero) & care & delta, care & delta, care & ~delta & (value ^ zero)


class NLDM:
    def __init__(self, library, slew_ps=20.):
        self.library, self.slew_ps = library, slew_ps

    def __call__(self, spec, background_ff=0.):
        graph = nldm.compile_graph(spec, self.library)
        if background_ff:
            for load in graph[1][:graph[0]]:
                load[0] += background_ff
                load[1] += background_ff
        result = nldm.evaluate_python(graph, self.library, self.slew_ps)
        result['outputs_ps'] = [max(result['arrivals_ps'][o]) for o in graph[3]]
        return result


class Oracle:
    def __init__(self, structures, measure, library, paths=None, load_ff=5.):
        self.structures, self.measure, self.library = structures, measure, library
        self.paths, self.load_ff = paths, load_ff
        self.backend = SimpleNamespace(paths=paths)
        self.native_screen = False
        self.cache = OrderedDict()
        self.stats = dict(measurements=0, cache_hits=0)

    def compiled(self, roots):
        spec, occurrences = self.structures.graph(roots, self.load_ff)
        return spec, nldm.compile_graph(spec, self.library), occurrences

    def _complete(self, roots):
        key = tuple(roots)
        if key not in self.cache:
            spec, _ = self.structures.graph(roots, self.load_ff)
            result = self.measure(spec)
            result['gate_count'] = result.get('gate_count', len(spec['gates']))
            result['max_depth'] = result.get('max_depth', max(self.structures.nodes[i].depth for i in roots))
            result['theoretical_fs'] = max(self.structures.nodes[i].theoretical_fs for i in roots)
            self.cache[key] = result
            self.stats['measurements'] += 1
            if len(self.cache) > 512:
                self.cache.popitem(last=False)
        else:
            self.cache.move_to_end(key)
            self.stats['cache_hits'] += 1
        return dict(self.cache[key])

    def evaluate(self, roots, exact=False):
        if not exact and self.paths is not None and len(roots) == 1:
            score = self.paths.lookup_structure(self.structures, roots[0])
            if score is not None:
                return dict(delay_ps=score, ranking_kind='characterized-path')
        result = self._complete(roots)
        result.update(lower_ps=result['delay_ps'], upper_ps=result['delay_ps'])
        return result

    def regional_score(self, root, background_ff=0.):
        spec, _ = self.structures.graph([root], self.load_ff)
        return self.measure(spec, background_ff=background_ff)['delay_ps']

    def audit(self, roots):
        return self._complete(roots)
