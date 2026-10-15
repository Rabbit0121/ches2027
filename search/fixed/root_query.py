"""Exact root queries over a complete common-deadline child domain."""
from ...core.model import ARITY,gate,pins
from .accelerators import cover,common_center_pair,weighted_exceptions,PartialIndex

def root_query(p,domain,target,root,check=lambda:None,use_lp=False):
    values=sorted(domain);mask=p.mask;meta={}
    if not values:return None,meta
    if root=='INV':
        f=target^mask
        return (['INV',domain[f][1]] if f in domain else None),meta
    if root=='BUF':
        return (['BUF',domain[target][1]] if target in domain else None),meta
    if root in ('XOR2','XNOR2'):
        wanted=target if root=='XOR2' else target^mask
        for i,f in enumerate(values):
            if i%1024==0:check()
            if f^wanted in domain:return [root,domain[f][1],domain[f^wanted][1]],meta
        return None,meta
    if root.startswith(('NAND','AND','NOR','OR')):
        complement=root.startswith(('NAND','AND'))
        wanted=target if root.startswith(('NAND','OR')) else mask^target
        mapping={mask^f if complement else f:f for f in values if ((mask^f if complement else f)&~wanted)==0}
        # A zero target cover requires a real constant witness, never a free 0/1.
        if wanted==0:
            if 0 not in mapping:return None,meta
            answer=[0]
        else:
            if ARITY[root]==2:
                weights=[int((wanted>>b)&1) for b in range(mask.bit_length())]
                if use_lp:
                    from .accelerators import propose_weights
                    weights=propose_weights(mapping,wanted,check)
                cert=weighted_exceptions(mapping,wanted,weights);meta['weighted']=cert
                if cert['status']=='NO':return None,meta
                if cert['status']=='SAT':answer=cert['covers']
                else:answer,meta['cover']=cover(mapping,wanted,2,check)
            else:answer,meta['cover']=cover(mapping,wanted,ARITY[root],check)
        if answer is None:return None,meta
        answer += [answer[0]]*(ARITY[root]-len(answer))
        return [root,*[domain[mapping[c]][1] for c in answer]],meta
    if root=='OAI21':
        z=mask^target
        centers=[mask^f for f in values if f&z==z]
        answer,meta=common_center_pair(values,centers,target,mask,check)
        if answer is None:return None,meta
        a,b,c=answer
        return [root,domain[a][1],domain[b][1],domain[mask^c][1]],meta
    if root=='MUX2':
        index=PartialIndex(values,target,mask)
        for i,c in enumerate(values):
            if i%256==0:check()
            care_a=mask^c;care_b=c
            # Check the more constrained arm first, then short-circuit failures.
            first,second=(care_a,care_b) if care_a.bit_count()>=care_b.bit_count() else (care_b,care_a)
            a=index.match(first)
            if a is None:continue
            b=index.match(second)
            if b is None:continue
            if first!=care_a:a,b=b,a
            return [root,domain[a][1],domain[b][1],domain[c][1]],meta
        return None,meta
    # Truth-table-driven fallback has no assumptions about gate monotonicity.
    from .relation import root_match
    return root_match(p,domain,target,root,check)

def decide_domains(p,target,bound,seconds,max_states,use_lp=False,max_depth=None,matcher='auto'):
    from .generic import Search
    return Search(p,seconds,max_states,matcher,use_lp=use_lp).decide(target,bound,max_depth)
