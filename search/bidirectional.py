"""Forward generation, retained physical alternatives, and pending reverse requests."""
from ..timing.oracle import invert_pin
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from itertools import product
import json
import random
import time
from ..core.structure import Structures, ARITY

@dataclass
class Config:
    seconds: float = 60.0
    max_states: int = 3000
    variants_per_truth: int = 12
    expansion_width: int = 32
    reverse_width: int = 24
    max_demands: int = 128
    max_subscribers: int = 16
    max_depth: int | None = None
    demand_depth: int = 6
    forward_round_steps: int = 1200
    sharing: bool = True
    slew_ps: float = 20.0
    output_load_ff: float = 5.0
    timing: str = 'measured'
    seed: int = 0
    screen: str = 'auto'

class Archive:

    def __init__(self, structures, oracle, config):
        self.s, self.oracle, self.config = (structures, oracle, config)
        self.by_truth, self.records, self.seen = ({}, {}, set())
        self.version = 0
        self.size = 0
        self.truth_order, self.truth_ones = ([], [0] * (1 << structures.problem.n))
        self.match_cache = OrderedDict()
        self.stats = dict(offered=0, kept=0, resource_drops=0, depth_drops=0, same_truth_alternatives=0)

    def offer(self, i, force=False):
        if i in self.seen:
            return False
        self.seen.add(i)
        self.stats['offered'] += 1
        node = self.s.nodes[i]
        if self.config.max_depth is not None and node.depth > self.config.max_depth:
            self.stats['depth_drops'] += 1
            return False
        old = self.by_truth.get(node.truth, [])
        free = self.config.max_states - self.size
        capacity = min(self.config.variants_per_truth, len(old) + max(0, free))
        if not force and capacity == 0:
            self.stats['resource_drops'] += 1
            return False
        estimate = self.oracle.evaluate([i], exact=self.oracle.native_screen)
        _, graph, _ = self.oracle.compiled([i])
        o = graph[3][0]
        measured = self.config.timing == 'measured'
        record = dict(id=i, truth=hex(node.truth), depth=node.depth, theoretical_fs=node.theoretical_fs, nominal_ps=estimate['delay_ps'], lower_ps=None if measured else estimate['lower_ps'], upper_ps=None if measured else estimate['upper_ps'], ranking_kind=estimate.get('ranking_kind', 'NLDM'), input_capacitances_ff=graph[1][:graph[0]], output_slews_ps=None if measured else estimate['slews_ps'][o], gate_count=len(graph[2]))
        self.records[i] = record
        choices = old + [i]
        if len(choices) > capacity and (not force):
            keys = [lambda j: self.records[j]['nominal_ps'], lambda j: self.records[j]['depth'], lambda j: sum((sum(x) for x in self.records[j]['input_capacitances_ff'])), lambda j: max(self.records[j]['output_slews_ps'] or [0.0]), lambda j: self.records[j]['gate_count']]
            ordered = [sorted(choices, key=lambda j: (key(j), j)) for key in keys]
            keep = []
            for rank in range(len(choices)):
                for order in ordered:
                    if order[rank] not in keep:
                        keep.append(order[rank])
                    if len(keep) >= capacity:
                        break
                if len(keep) >= capacity:
                    break
            self.stats['resource_drops'] += len(choices) - len(keep)
            choices = keep
        if i not in choices:
            self.records.pop(i, None)
            return False
        if node.truth not in self.by_truth:
            bit = 1 << len(self.truth_order)
            self.truth_order.append(node.truth)
            f = node.truth
            while f:
                low = f & -f
                self.truth_ones[low.bit_length() - 1] |= bit
                f ^= low
            self.match_cache.clear()
        self.size += len(choices) - len(old)
        self.by_truth[node.truth] = choices
        for removed in set(old) - set(choices):
            self.records.pop(removed, None)
        if not measured:
            record['regional_nominal_ps'] = self.oracle.regional_score(i)
            record['regional_background_5ff_ps'] = self.oracle.regional_score(i, 5.0)
        self.stats['kept'] += 1
        self.stats['same_truth_alternatives'] += bool(old)
        self.version += 1
        return True

    def ids(self, depth=None):
        return [i for group in self.by_truth.values() for i in group if depth is None or self.s.nodes[i].depth <= depth]

    def selected(self, width, depth=None):
        groups = [[i for i in group if depth is None or self.s.nodes[i].depth <= depth] for group in self.by_truth.values()]
        groups = [sorted(group, key=lambda i: (self.records[i].get('regional_background_5ff_ps', self.records[i]['nominal_ps']), i)) for group in groups if group]
        targets = self.s.problem.targets
        groups.sort(key=lambda a: (min(((self.s.truth(a[0]) ^ f).bit_count() for f in targets)), self.records[a[0]]['nominal_ps'], a[0]))
        result = []

        def selection():
            if not self.config.seed:
                return result[:width]
            keep = max(1, width // 2)
            tail = result[keep:]
            random.Random(self.config.seed + self.version).shuffle(tail)
            return (result[:keep] + tail)[:width]
        for rank in range(max(map(len, groups), default=0)):
            for group in groups:
                if rank < len(group):
                    result.append(group[rank])
                    if len(result) >= width * (3 if self.config.seed else 1):
                        return selection()
        return selection()

    def matching(self, value, care, depth=None):
        if care == self.s.problem.mask:
            groups = [self.by_truth.get(value & care, ())]
        else:
            key = (value & care, care)
            if key in self.match_cache:
                bits = self.match_cache[key]
                self.match_cache.move_to_end(key)
            else:
                bits = (1 << len(self.truth_order)) - 1
                todo = care
                while todo and bits:
                    low = todo & -todo
                    column = self.truth_ones[low.bit_length() - 1]
                    bits &= column if value & low else ~column
                    todo ^= low
                self.match_cache[key] = bits
                if len(self.match_cache) > 256:
                    self.match_cache.popitem(last=False)
            groups = []
            while bits:
                low = bits & -bits
                groups.append(self.by_truth[self.truth_order[low.bit_length() - 1]])
                bits ^= low
        return [i for group in groups for i in group if depth is None or self.s.nodes[i].depth <= depth]

@dataclass(eq=False)
class Demand:
    value: int
    care: int
    depth: int
    output: int | None = None
    users: list = field(default_factory=list)
    resolved: set = field(default_factory=set)
    provisional_contracts: list = field(default_factory=list)

class Search:

    def __init__(self, problem, oracle_factory, config=None):
        self.p, self.config = (problem, config or Config())
        if self.config.timing not in ('measured', 'nldm'):
            raise ValueError('Unknown timing objective')
        self.structures = Structures(problem)
        c = self.config
        self.oracle = oracle_factory(self.structures)
        self.archive = Archive(self.structures, self.oracle, c)
        self.roots = [None] * problem.m
        self.best, self.events = (None, [])
        self.stats = dict(forward_steps=0, reverse_prefixes=0, reverse_matches=0, candidate_submissions=0, certified_rejections=0, demands_created=0, demands_resolved=0, demand_resource_drops=0, recursive_compositions=0, forward_rounds=0, reverse_rounds=0)
        self.demands, self.demand_keys = ([], {})
        self.started = time.monotonic()
        self.deadline = self.started + c.seconds
        self.jobs = deque()
        self.scheduled = set()
        self.variant_versions = set()
        self.forward_depth = 2
        self.initialise()

    def initialise(self):
        from .fixed.adaptive import initial
        for raw in range(self.p.n):
            for kind in ('BUF', 'INV'):
                self.offer(self.structures.make(kind, (-raw-1,)), 'input', submit=False)
        expressions = initial(self.p, self.config.max_depth)
        for j, expression in expressions.items():
            root = self.structures.import_expression(expression)
            for node in sorted(self.structures.descendants(root)):
                self.offer(node, 'initial', submit=False)
            self.submit(j, root, 'initial')
        self.initial_roots = list(self.roots)
        self.initial = self.best
        for j, target in enumerate(self.p.targets):
            self.request(target, self.p.mask, self.config.max_depth or self.config.demand_depth, output=j)

    def objective(self, audit):
        if self.config.timing == 'fixed':
            return (audit['theoretical_fs'], audit['gate_count'])
        return (audit['delay_ps'], sum(audit['outputs_ps']), audit['gate_count'])

    def offer(self, i, source, submit=True, force=False):
        accepted = self.archive.offer(i, force)
        if submit:
            for j, f in enumerate(self.p.targets):
                if self.structures.truth(i) == f:
                    self.submit(j, i, source)
        if accepted:
            for need in list(self.demands):
                if not (self.structures.truth(i) ^ need.value) & need.care and self.structures.nodes[i].depth <= need.depth:
                    self.resolve(need, i)
        return accepted

    def submit(self, j, i, source):
        if self.config.max_depth is not None and self.structures.nodes[i].depth > self.config.max_depth:
            return False
        if self.roots[j] == i:
            return False
        self.stats['candidate_submissions'] += 1
        roots = list(self.roots)
        roots[j] = i
        return self.submit_roots(roots, source, j, i)

    def submit_roots(self, roots, source, j=None, i=None):
        if len(roots) != self.p.m:
            raise ValueError('Joint output count mismatch')
        if self.config.max_depth is not None and any((self.structures.nodes[r].depth > self.config.max_depth for r in roots if r is not None)):
            return False
        if any((self.structures.truth(r) != self.p.targets[k] for k, r in enumerate(roots) if r is not None)):
            raise ValueError('Joint substitution changed an output function')
        if any((x is None for x in roots)):
            self.roots = list(roots)
            return True
        actual = self.oracle.evaluate(roots, exact=True)
        if self.best and actual['delay_ps'] > self.best['delay_ps'] + 1e-08:
            return False
        audit = self.oracle.audit(roots)
        if self.config.max_depth is not None and audit['max_depth'] > self.config.max_depth:
            return False
        if self.best and self.objective(audit) >= self.objective(self.best):
            return False
        old = self.best
        self.roots, self.best = (roots, audit)
        self.events.append(dict(source=source, output=j, structure=i, before_ps=old['delay_ps'] if old else None, after_ps=audit['delay_ps'], before_theoretical_fs=old['theoretical_fs'] if old else None, after_theoretical_fs=audit['theoretical_fs'], seconds=time.monotonic() - self.started))
        return True

    def resolve(self, need, i):
        if i in need.resolved:
            return
        need.resolved.add(i)
        self.stats['demands_resolved'] += 1
        if need.output is not None:
            self.submit(need.output, i, 'reverse demand')
        for kind, prefix, parent in list(need.users):
            result = self.structures.make(kind, (*prefix, i))
            self.stats['recursive_compositions'] += 1
            if (self.structures.truth(result) ^ parent.value) & parent.care:
                raise ValueError('Invalid inverse relation witness')
            self.offer(result, 'recursive demand')

    def request(self, value, care, depth, output=None, user=None, contract=None):
        if depth < 1:
            return None
        key = (value & care, care, depth, output)
        if key not in self.demand_keys:
            if len(self.demands) >= self.config.max_demands:
                self.stats['demand_resource_drops'] += 1
                return None
            need = Demand(value & care, care, depth, output)
            self.demand_keys[key] = need
            self.demands.append(need)
            self.stats['demands_created'] += 1
            self.enqueue_reverse(need)
        need = self.demand_keys[key]
        if user is not None and user not in need.users:
            if len(need.users) < self.config.max_subscribers:
                need.users.append(user)
                for i in sorted(need.resolved):
                    kind, prefix, parent = user
                    result = self.structures.make(kind, (*prefix, i))
                    self.offer(result, 'cached reverse demand')
            else:
                self.stats['demand_resource_drops'] += 1
        if contract is not None:
            need.provisional_contracts.append(contract)
        for i in self.archive.matching(need.value, need.care, need.depth):
            self.resolve(need, i)
        return need

    def enqueue_reverse(self, need):
        candidates = tuple(self.archive.selected(self.config.reverse_width, need.depth - 1))
        for kind in self.p.costs:
            if need.depth < 2:
                continue
            key = ('reverse', id(need), kind, candidates)
            if key not in self.scheduled:
                self.scheduled.add(key)
                self.jobs.append(('reverse', self.reverse_job(need, kind, candidates)))

    def reverse_job(self, need, kind, candidates):
        arity = ARITY[kind]
        for prefix in product(candidates, repeat=arity - 1):
            self.stats['reverse_prefixes'] += 1
            value, care, bad = invert_pin(self.structures, kind, prefix, need.value, need.care)
            if not bad:
                matches = self.archive.matching(value, care, need.depth - 1)
                if self.config.timing == 'measured':
                    table = self.oracle.backend.paths
                    ranks = {i: table.extended_score(self.structures, i, kind) for i in matches}
                    matches = sorted(matches, key=lambda i: (ranks[i] is None, ranks[i] if ranks[i] is not None else 0.0, i))
                for i in matches:
                    if time.monotonic() >= self.deadline:
                        return
                    result = self.structures.make(kind, (*prefix, i))
                    self.stats['reverse_matches'] += 1
                    self.offer(result, 'reverse root match')
                    yield
                if not matches and need.depth > 2:
                    contract = None
                    self.request(value, care, need.depth - 1, user=(kind, prefix, need), contract=contract)
            yield

    def enqueue_forward(self):
        candidates = tuple(self.archive.selected(self.config.expansion_width, self.forward_depth - 1))
        added = 0
        for kind in self.p.costs:
            key = ('forward', kind, candidates, self.forward_depth)
            if candidates and key not in self.scheduled:
                self.scheduled.add(key)
                self.jobs.append(('forward', self.forward_job(kind, candidates, self.forward_depth)))
                added += 1
        if added:
            self.stats['forward_rounds'] += 1
        return added

    def forward_job(self, kind, candidates, depth):
        shallow = tuple((i for i in candidates if self.structures.nodes[i].depth < depth - 1))
        highest = tuple((i for i in candidates if self.structures.nodes[i].depth == depth - 1))
        eligible = shallow + highest
        for pivot in range(ARITY[kind]):
            groups = [shallow] * pivot + [highest] + [eligible] * (ARITY[kind] - pivot - 1)
            for args in product(*groups):
                i = self.structures.make(kind, args)
                self.offer(i, 'forward image')
                self.stats['forward_steps'] += 1
                yield

    def run(self):
        self.enqueue_forward()
        self.enqueue_variants()
        since_round = getattr(self, '_since_round', 0)
        while time.monotonic() < self.deadline:
            if not self.jobs:
                if self.config.max_depth is not None and self.forward_depth >= self.config.max_depth:
                    break
                maximum = max((self.structures.nodes[i].depth for i in self.archive.ids()), default=0)
                self.forward_depth = min(self.forward_depth + 1, maximum + 1)
                self.enqueue_forward()
                for need in list(self.demands):
                    self.enqueue_reverse(need)
                self.enqueue_variants()
                self.stats['reverse_rounds'] += 1
                if not self.jobs:
                    self.stop_reason = 'resource-retained frontier exhausted; not a global exclusion'
                    break
            kind, job = self.jobs.popleft()
            try:
                next(job)
                self.jobs.append((kind, job))
                since_round += 1
            except StopIteration:
                pass
            if since_round >= self.config.forward_round_steps:
                since_round = 0
                if self.config.max_depth is None or self.forward_depth < self.config.max_depth:
                    maximum = max((self.structures.nodes[i].depth for i in self.archive.ids()), default=0)
                    self.forward_depth = min(self.forward_depth + 1, maximum + 1)
                    self.enqueue_forward()
                self.stats['reverse_rounds'] += 1
                for need in list(self.demands):
                    self.enqueue_reverse(need)
                self.enqueue_variants()
        self._since_round = since_round
        return self.report()

    def enqueue_variants(self):
        if any((i is None for i in self.roots)):
            return
        version = tuple(self.roots)
        if version in self.variant_versions:
            return
        self.variant_versions.add(version)
        self.jobs.appendleft(('physical_variants', self.variant_job(version)))

    def variant_job(self, roots):
        nodes = set().union(*(self.structures.descendants(i) for i in roots))
        for i in sorted(nodes, reverse=True):
            for replacement in self.structures.pin_variants(i):
                candidate = self.structures.rewire(roots, i, replacement)
                self.submit_roots(candidate, 'physical pin variant')
                self.offer(replacement, 'physical pin variant', submit=False)
                yield

    def report(self):
        if all((i is not None for i in self.roots)):
            final = self.oracle.audit(self.roots)
            self.best = final
        else:
            final = None
        return dict(status='FEASIBLE' if final else 'INCOMPLETE', engine='measured-bidirectional', initial=self.initial, final=final, roots=self.roots, events=self.events, search_stats=self.stats, archive_stats=self.archive.stats, timing_stats=self.oracle.stats, archive_functions=len(self.archive.by_truth), archive_structures=len(self.archive.ids()), pending_jobs=len(self.jobs), seconds=time.monotonic() - self.started, stop_reason=getattr(self, 'stop_reason', 'wall-clock or explicit depth resource'), global_optimality_proved=False, resource_scope='bounded structural variants, prefix sampling, finite demand depth and wall clock', timing_scope='configured EDA-flow implementation timing; path-table ranking is heuristic' if self.config.timing == 'measured' else 'fixed-PVT zero-wire NLDM')
