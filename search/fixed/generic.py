"""Complete cost/depth recursion plus target matching; no fixed layer template."""
from .exact import Domains,Incomplete
from ...core.model import ARITY


def expression_depth(expression):
    if isinstance(expression,str):return 0
    return 1+max(expression_depth(e) for e in expression[1:])


class Search:
    def __init__(self,p,seconds=120,max_states=1000000,matcher='auto',block_size=512,use_lp=False):
        if matcher not in ('auto','relation'):raise ValueError('Unknown matcher')
        self.p=p;self.domains=Domains(p,seconds,max_states);self.matcher=matcher
        self.block_size=block_size;self.cache={};self.best={};self.queries=[]
        self.use_lp=use_lp

    def decide(self,target,bound,max_depth):
        p=self.p
        effective=bound//min(p.costs.values())
        if max_depth is not None:effective=min(effective,max_depth)
        key=target,bound,effective
        if key in self.cache:return self.cache[key]
        rows=[]
        def finish(status,expression=None):
            result=dict(status=status,bound_fs=bound,max_depth=max_depth,effective_depth=effective,roots=rows)
            if expression is not None:
                f,t=p.expression(expression);h=expression_depth(expression)
                if f!=target or t>bound or h>effective:raise ValueError('Invalid bounded-depth witness')
                result.update(expression=expression,arrival_fs=t,depth=h)
            if status!='UNKNOWN':self.cache[key]=result
            return result
        if effective<1:return finish('UNSAT')
        for x in p.inputs:
            for g in ('BUF','INV'):
                e=[g,x];f,t=p.expression(e)
                if f==target and t<=bound:return finish('SAT',e)
        if effective==1:return finish('UNSAT')
        # Larger root fees leave smaller child domains. This only orders work;
        # every non-dominated root remains in the complete decision procedure.
        for root,cost in sorted(p.costs.items(),key=lambda item:(-item[1],item[0])):
            if root=='BUF':continue
            try:
                pool=self.domains.build(bound-cost,effective-1)
                if self.matcher=='relation':
                    from .relation import root_match
                    expr,stats=root_match(p,pool,target,root,self.domains.check,self.block_size)
                else:
                    from .root_query import root_query
                    expr,stats=root_query(p,pool,target,root,self.domains.check,self.use_lp)
                rows.append(dict(root=root,status='SAT' if expr is not None else 'UNSAT',
                    child_budget_fs=bound-cost,child_max_depth=effective-1,functions=len(pool),stats=stats))
                if expr is not None:return finish('SAT',expr)
            except (Incomplete,RecursionError) as err:
                rows.append(dict(root=root,status='UNKNOWN',reason=str(err) or 'recursion resource limit'))
        return finish('UNSAT' if all(r['status']=='UNSAT' for r in rows) else 'UNKNOWN')

    def optimize(self,max_depth=None,checkpoint=None,stop_after_first=False):
        if max_depth is not None and (type(max_depth) is not int or max_depth<1):
            raise ValueError('Depth must be a positive integer')
        p=self.p;lower=min(p.costs[g] for g in ('INV','BUF'))-1;upper=None
        ceiling=(max(p.costs[g] for g in ('INV','BUF'))+(max_depth-1)*max(p.costs.values())
                 if max_depth is not None else None)
        bound=lower+1;status='INCOMPLETE';reason=None
        def report():
            return dict(status=status,reason=reason,max_depth=max_depth,
                optimal_within_depth=status=='OPTIMAL_WITHIN_DEPTH',
                global_optimality_proved=status=='OPTIMAL',matcher=self.matcher,
                lower_bound_fs=lower+1,upper_bound_fs=upper,queries=self.queries,
                domain_tuples=self.domains.tuples,depth_includes_input_BUF_INV=True)
        try:
            while True:
                results=[];state='SAT'
                for j,target in enumerate(p.targets):
                    result=self.decide(target,bound,max_depth)
                    results.append(dict(output=j,**result))
                    if result['status']=='SAT':
                        if j not in self.best or result['arrival_fs']<p.expression(self.best[j])[1]:
                            self.best[j]=result['expression']
                    elif result['status']=='UNSAT':state='UNSAT';break
                    else:state='UNKNOWN'
                self.queries.append(dict(bound_fs=bound,status=state,outputs=results))
                if len(self.best)==p.m:upper=max(p.expression(e)[1] for e in self.best.values())
                if state=='UNKNOWN':reason='Incomplete query; no lower bound was advanced';break
                if state=='UNSAT':lower=bound
                if upper is not None and lower>=upper:raise ValueError('Conflicting feasible/infeasible bounds')
                if upper is not None and lower+1>=upper:
                    status='OPTIMAL' if max_depth is None else 'OPTIMAL_WITHIN_DEPTH';break
                if upper is not None and stop_after_first:
                    status='FEASIBLE' if max_depth is None else 'FEASIBLE_WITHIN_DEPTH';break
                if state=='UNSAT' and ceiling is not None and bound==ceiling:
                    status='NO_SOLUTION_WITHIN_DEPTH';break
                if checkpoint:checkpoint(report(),self.best)
                if upper is not None:bound=(lower+upper)//2
                else:bound=min(2*bound,ceiling) if ceiling is not None else 2*bound
        except (KeyboardInterrupt,RecursionError) as err:
            reason='interrupted' if isinstance(err,KeyboardInterrupt) else 'recursion resource limit'
        final=report()
        if checkpoint:checkpoint(final,self.best)
        return final,self.best
