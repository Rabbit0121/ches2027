"""Target-directed exact finite-domain primitives, independent of any APN answer.

A NO result concerns the supplied domain only. Global use requires a complete
deadline domain (or a separately proved feasibility basis).
"""
from functools import lru_cache

def bits(mask):
    while mask:
        bit=mask & -mask;mask^=bit;yield bit.bit_length()-1

def posting(values,care):
    """Packed-byte construction avoids repeated growing-bigint allocations."""
    rows={b:bytearray((len(values)+7)//8) for b in bits(care)}
    for i,value in enumerate(values):
        for b in bits(value & care): rows[b][i>>3] |= 1 << (i&7)
    return {b:int.from_bytes(data,'little') for b,data in rows.items()}

def maximal(values):
    kept=[]
    for value in sorted(set(values),key=lambda v:(-v.bit_count(),v)):
        if not any(value & ~other == 0 for other in kept): kept.append(value)
    return kept

class PartialIndex:
    """Fixed-target partial-care matches; 4-bit exact block intersections."""
    def __init__(self,values,target,mask):
        self.values=list(values);self.full=(1<<len(values))-1;self.mask=mask
        good=[mask^(f^target) for f in self.values];posts=posting(good,mask)
        self.blocks=[]
        for offset in range(0,mask.bit_length(),4):
            table=[self.full]*16
            for subset in range(1,16):
                bit=subset & -subset;b=offset+bit.bit_length()-1
                table[subset]=table[subset^bit]&posts.get(b,self.full)
            self.blocks.append(table)
    def match(self,care):
        ids=self.full
        for i,table in enumerate(self.blocks):
            ids &= table[(care>>(4*i))&15]
            if not ids:return None
        return self.values[(ids&-ids).bit_length()-1] if ids else None

def weighted_exceptions(covers,wanted,weights):
    """Exact integer check, including all heavy exceptions and their residuals.

    Zero-weight bits remain in masks; no unsafe positive-support dominance.
    Returns a two-cover witness or a finite-domain exclusion certificate.
    """
    if any(type(w) is not int or w<0 for w in weights): raise ValueError('Nonnegative integer weights required')
    if any(b>=len(weights) for b in bits(wanted)): raise ValueError('Missing weights')
    values=sorted(set(c for c in covers if c & ~wanted == 0))
    weight=lambda c:sum(weights[b] for b in bits(c))
    total=weight(wanted)
    if not total: return dict(status='NOT_APPLICABLE')
    low=(total-1)//2
    exceptions=[c for c in values if weight(c)>low]
    posts=posting(values,wanted);full=(1<<len(values))-1
    residuals=[]
    for c in exceptions:
        residual=wanted & ~c; candidates=full
        for b in bits(residual): candidates &= posts[b]
        if candidates:
            d=values[(candidates & -candidates).bit_length()-1]
            return dict(status='SAT',covers=[c,d])
        residuals.append(residual)
    return dict(status='NO',total_weight=total,ordinary_upper=low,
        exceptional_masks=exceptions,residuals=residuals,domain_size=len(values))

def propose_weights(covers,wanted,check=lambda:None):
    """LP cutting plane proposes weights; integer rechecking supplies the evidence.

    Optional scipy. Any rounding weakness costs speed, never correctness.
    """
    import numpy as np
    from scipy.optimize import linprog
    bs=list(bits(wanted));values=sorted(set(covers));active=values[:min(32,len(values))]
    if not active: return [int(i in bs) for i in range(wanted.bit_length())]
    for _ in range(30):
        check()
        matrix=np.array([[(c>>b)&1 for b in bs] for c in active],dtype=float)
        res=linprog(-np.ones(len(bs)),A_ub=matrix,b_ub=np.ones(len(active)),bounds=(0,1),method='highs',options={'time_limit':0.1})
        if not res.success: break
        scores=[sum(res.x[i] for i,b in enumerate(bs) if (c>>b)&1) for c in values]
        violating=sorted((i for i,v in enumerate(scores) if v>1+1e-8),key=lambda i:-scores[i])[:32]
        new=[values[i] for i in violating if values[i] not in active]
        if not new: break
        active.extend(new)
    else: pass
    weights=[0]*wanted.bit_length()
    if res.success:
        for b,v in zip(bs,res.x): weights[b]=max(0,round(float(v)*1000000))
    if not any(weights):
        for b in bs: weights[b]=1
    return weights

def cover(covers,wanted,slots,check=lambda:None):
    """Common-deadline dominance, rare-bit branching and exact failed-state cache."""
    values=maximal(c for c in covers if c and c & ~wanted == 0)
    posts=posting(values,wanted); full=(1<<len(values))-1; failed=set();steps=0
    def visit(rem,k):
        nonlocal steps
        steps+=1
        if steps%256==0: check()
        if rem==0: return []
        if k==0 or (rem,k) in failed: return None
        # A cheap uniform-weight inequality; all arithmetic is exact.
        if not values or k*max((v&rem).bit_count() for v in values)<rem.bit_count():
            failed.add((rem,k));return None
        if k==1:
            ids=full
            for b in bits(rem): ids &= posts.get(b,0)
            if ids: return [values[(ids&-ids).bit_length()-1]]
        else:
            b=min(bits(rem),key=lambda b:posts.get(b,0).bit_count())
            ids=posts.get(b,0);seen=set()
            while ids:
                bit=ids & -ids;ids^=bit;i=bit.bit_length()-1;r=rem & ~values[i]
                if r in seen: continue
                seen.add(r);tail=visit(r,k-1)
                if tail is not None: return [values[i],*tail]
        failed.add((rem,k));return None
    check();witness=visit(wanted,slots)
    return witness,dict(states=steps,failed_states=len(failed),domain_size=len(values))

def common_center_pair(functions,centers,target,mask,check=lambda:None):
    """Dual-tree OAI21 test preserving common-center compatibility.

    centers are zero sets of legal c with c=1 on Z. A pair is legal iff
    (a|b)&Z=Z and (a|b)&Y is contained in one center zero set.
    """
    Y=target;Z=mask^Y;centers=maximal(centers)
    if any(c&~Y for c in centers): raise ValueError('Invalid center mask')
    @lru_cache(None)
    def compatible(need): return next((c for c in centers if need&~c==0),None)
    values=sorted(set(f for f in functions if compatible(f&Y) is not None),key=lambda f:(f&Y,f&Z))
    def build(rows):
        must=Y;may=0
        for f in rows: must &= f&Y;may |= f&Z
        children=None
        if len(rows)>8:
            m=len(rows)//2;children=build(rows[:m]),build(rows[m:])
        return rows,must,may,children
    root=build(values);visits=0
    def join(a,b,same=False):
        nonlocal visits
        visits+=1
        if visits%256==0: check()
        if compatible(a[1]|b[1]) is None or (a[2]|b[2])!=Z: return None
        if a[3] is None and b[3] is None:
            for i,f in enumerate(a[0]):
                for g in b[0][i if same else 0:]:
                    c=compatible((f|g)&Y)
                    if c is not None and (f|g)&Z==Z: return f,g,c
            return None
        if same:
            l,r=a[3]
            return join(l,l,True) or join(l,r) or join(r,r,True)
        if a[3] and (not b[3] or len(a[0])>=len(b[0])):
            return join(a[3][0],b) or join(a[3][1],b)
        return join(a,b[3][0]) or join(a,b[3][1])
    check();answer=join(root,root,True) if values else None
    return answer,dict(tree_pairs=visits,functions=len(values),centers=len(centers))
