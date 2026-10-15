"""Truth-table-driven gate matching, independent of gate names or depth.

table[sum(pin[i] << i)] is the scalar gate output. Ordered tuples and repeated
pins are retained. Blocking reduces memory, never removes candidates.
"""
from itertools import product, islice


def match(table, domains, target, mask, check=lambda: None, block_size=512):
    arity=len(domains)
    if arity<1 or len(table)!=1<<arity or any(v not in (0,1) for v in table):
        raise ValueError('Invalid gate truth table')
    if block_size<1 or mask<1 or mask & (mask+1) or target<0 or target & ~mask:
        raise ValueError('Invalid mask, target or block size')
    domains=[tuple(sorted(set(d))) for d in domains]
    if any(f<0 or f&~mask for domain in domains for f in domain):
        raise ValueError('Function outside truth universe')
    stats=dict(right_blocks=0,right_tuples=0,left_tuples=0,intersections=0)
    check()
    if any(not d for d in domains):return None,stats
    left_count=arity//2;right_count=arity-left_count
    codes=1<<right_count;all_codes=(1<<codes)-1;width=mask.bit_length()
    allowed=[[sum(1<<b for b in range(codes) if table[a|(b<<left_count)]==y)
              for a in range(1<<left_count)] for y in (0,1)]
    right_iter=product(*domains[left_count:])
    while True:
        check();right=list(islice(right_iter,block_size))
        if not right:break
        stats['right_blocks']+=1;stats['right_tuples']+=len(right)
        byte_count=(len(right)+7)//8
        packed=[[bytearray(byte_count) for _ in range(codes)] for _ in range(width)]
        for i,fs in enumerate(right):
            if i%128==0:check()
            for b in range(codes):
                positions=mask
                for j,f in enumerate(fs):positions &= f if (b>>j)&1 else mask^f
                while positions:
                    bit=positions&-positions;positions^=bit;x=bit.bit_length()-1
                    packed[x][b][i>>3] |= 1<<(i&7)
        posts=[[int.from_bytes(v,'little') for v in row] for row in packed]
        full=(1<<len(right))-1;unions={}
        for left in product(*domains[:left_count]):
            stats['left_tuples']+=1
            if stats['left_tuples']%128==0:check()
            constraints=[];impossible=False
            for x in range(width):
                a=sum(((f>>x)&1)<<j for j,f in enumerate(left))
                allowed_codes=allowed[(target>>x)&1][a]
                if not allowed_codes:impossible=True;break
                if allowed_codes==all_codes:continue
                key=x,allowed_codes
                if key not in unions:
                    ids=0;bits=allowed_codes
                    while bits:
                        bit=bits&-bits;bits^=bit;ids |= posts[x][bit.bit_length()-1]
                    unions[key]=ids
                ids=unions[key]
                if not ids:impossible=True;break
                constraints.append(ids)
            if impossible:continue
            ids=full
            for constraint in sorted(constraints,key=int.bit_count):
                stats['intersections']+=1;ids &= constraint
                if not ids:break
            if ids:
                answer=(*left,*right[(ids&-ids).bit_length()-1])
                check();return answer,stats
    check();return None,stats


def root_match(p,domain,target,root,check=lambda:None,block_size=512):
    from ...core.model import ARITY,gate
    arity=ARITY[root]
    table=[gate(root,[(code>>i)&1 for i in range(arity)],1) for code in range(1<<arity)]
    answer,stats=match(table,[domain]*arity,target,p.mask,check,block_size)
    return (None if answer is None else [root,*[domain[f][1] for f in answer]]),stats
