"""Complete deadline domains; caps raise UNKNOWN, never return a truncated domain."""
import time
from ...core.model import gate, pins

class Incomplete(Exception): pass

class Domains:
    def __init__(self,p,seconds=0,max_states=1000000):
        self.p=p; self.cache={}; self.start=time.monotonic(); self.seconds=seconds
        self.max_states=max_states; self.tuples=0

    def check(self):
        if self.seconds and time.monotonic()-self.start >= self.seconds: raise Incomplete('time limit')

    def build(self,bound,depth=None):
        self.check(); p=self.p; minimum=min(p.costs.values())
        depth=min(bound//minimum,depth if depth is not None else bound//minimum)
        if depth<1: return {}
        key=bound,depth
        if key in self.cache: return self.cache[key]
        pool={}
        def offer(f,t,e):
            if f not in pool or t<pool[f][0]: pool[f]=t,e
            if len(pool)>self.max_states: raise Incomplete('state limit')
        for x in p.inputs:
            for g in ('BUF','INV'):
                if p.costs[g]<=bound:
                    f,t=p.expression([g,x]); offer(f,t,[g,x])
        if depth>1:
            smaller=self.build(bound-minimum,depth-1)
            for f,(t,e) in smaller.items(): offer(f,t,e)
            for g,cost in p.costs.items():
                if g=='BUF': continue # internal BUF is strictly dominated
                eligible=[(f,t,e) for f,(t,e) in sorted(smaller.items()) if t+cost<=bound]
                for ids in pins(g,len(eligible)):
                    self.tuples+=1
                    if self.tuples%1024==0: self.check()
                    args=[eligible[i] for i in ids]
                    f=gate(g,[a[0] for a in args],p.mask)
                    offer(f,cost+max(a[1] for a in args),[g,*[a[2] for a in args]])
        self.check(); self.cache[key]=pool
        return pool

def optimize(p,seconds=0,max_states=1000000,depth=None):
    if depth is not None and (type(depth) is not int or depth<1):raise ValueError('Invalid maximum depth')
    domains=Domains(p,seconds,max_states); budget=min(p.costs['BUF'],p.costs['INV'])
    ceiling=max(p.costs[g] for g in ('BUF','INV'))+(depth-1)*max(p.costs.values()) if depth is not None else None
    complete=0; expressions={}; events=[]
    try:
        while True:
            pool=domains.build(budget,depth)
            complete=budget
            expressions={j:pool[t][1] for j,t in enumerate(p.targets) if t in pool}
            events.append(dict(bound_fs=budget,functions=len(pool),found=len(expressions)))
            if len(expressions)==p.m:
                return dict(status='OPTIMAL' if depth is None else 'OPTIMAL_WITHIN_DEPTH',
                    global_optimality_proved=depth is None,max_depth=depth,events=events,tuples=domains.tuples),expressions
            if ceiling is not None and budget>=ceiling:
                return dict(status='NO_SOLUTION_WITHIN_DEPTH',global_optimality_proved=False,max_depth=depth,events=events),expressions
            next_events=[c for g,c in p.costs.items() if g in ('BUF','INV') and c>budget]
            # With a depth cap, a slower shallow representative can create the
            # next event even when a faster deeper representative already exists.
            # Keep the arrival frontier of EVERY possible child depth.
            event_times={t for t,e in pool.values()} if depth is None else {
                t for h in range(1,depth) for t,e in domains.build(budget,h).values()}
            next_events += [t+c for t in event_times for c in p.costs.values() if t+c>budget]
            if not next_events:
                if ceiling is not None:budget=ceiling;continue
                return dict(status='UNREACHABLE',global_optimality_proved=False,events=events),expressions
            budget=min(next_events)
            if ceiling is not None:budget=min(budget,ceiling)
    except (Incomplete,RecursionError) as e:
        return dict(status='INCOMPLETE',reason=str(e),global_optimality_proved=False,
            max_depth=depth,complete_through_fs=complete,events=events,tuples=domains.tuples),expressions

def baseline(p):
    """Balanced DNF upper bound. No optimum or target-specific topology is supplied."""
    if 'NAND2' not in p.costs: return {}
    positive=[['BUF',x] for x in p.inputs]; negative=[['INV',x] for x in p.inputs]
    def inv(a): return ['INV',a]
    def AND(a,b): return inv(['NAND2',a,b])
    def OR(a,b): return ['NAND2',inv(a),inv(b)]
    def reduce(items,op):
        if len(items)==1: return items[0]
        k=len(items)//2; return op(reduce(items[:k],op),reduce(items[k:],op))
    one=['NAND2',positive[0],negative[0]]; zero=inv(one)
    expressions={}
    for j,target in enumerate(p.targets):
        terms=[reduce([positive[i] if (x>>i)&1 else negative[i] for i in range(p.n)],AND)
               for x in range(1<<p.n) if (target>>x)&1]
        expressions[j]=reduce(terms,OR) if terms else zero
    return expressions
