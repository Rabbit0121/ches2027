"""Evidence-driven native discovery; starting circuits are synthesized from truth."""
import json
from pathlib import Path
import shutil
import subprocess
from .exact import baseline
from .generic import expression_depth
from .audit import audit
from ...core.model import emit


def initial(p,max_depth=None):
    """Compare paid DNF and ANF constructions; neither is a required topology."""
    candidates=[baseline(p)]
    if 'AND2' in p.costs and ('XOR2' in p.costs or 'XNOR2' in p.costs):
        def xor(a,b):
            options=[]
            if 'XOR2' in p.costs:options.append(['XOR2',a,b])
            if 'XNOR2' in p.costs:options.append(['INV',['XNOR2',a,b]])
            return min(options,key=lambda e:p.expression(e)[1])
        def reduce(items,op):
            if len(items)==1:return items[0]
            middle=len(items)//2
            return op(reduce(items[:middle],op),reduce(items[middle:],op))
        positive=[['BUF',x] for x in p.inputs]
        zero=xor(positive[0],positive[0]);one=['INV',zero]
        es={}
        for j in range(p.m):
            coefficients=[(v>>j)&1 for v in p.sbox]
            for i in range(p.n):
                for x in range(1<<p.n):
                    if x&(1<<i):coefficients[x]^=coefficients[x^(1<<i)]
            terms=[]
            for x,c in enumerate(coefficients):
                if c:terms.append(reduce([positive[i] for i in range(p.n) if x>>i&1],lambda a,b:['AND2',a,b]) if x else one)
            es[j]=reduce(terms,xor) if terms else zero
        candidates.append(es)
    answer={}
    for candidate in candidates:
        for j,e in candidate.items():
            if max_depth is not None and expression_depth(e)>max_depth:continue
            if j not in answer or p.expression(e)[1]<p.expression(answer[j])[1]:answer[j]=e
    return answer


def search(p,out,seconds=120,max_depth=None,max_states=1000000,slice_seconds=3.,max_demands=128,stop_after_first=False,feedback=True,covers=True,refresh=False,decision_log_max_bytes=50*1024*1024):
    if type(decision_log_max_bytes) is not int or not 0<=decision_log_max_bytes<2**63:
        raise ValueError('Decision log cap must be in 0..2**63-1 bytes')
    if p.n>6: raise ValueError('The fixed native core supports at most six input bits')
    pwsh=shutil.which('pwsh')
    if pwsh is None:raise RuntimeError('Adaptive discovery requires PowerShell 7 (pwsh) for the native kernels')
    if max(p.costs.values())>100000000:raise ValueError('Native gate costs exceed the supported integer range')
    expressions=initial(p,max_depth)
    original=audit(p,emit(expressions),partial=True)
    def write(name,value):
        path=out/name;tmp=path.with_suffix(path.suffix+'.tmp')
        tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
    write('initial.json',original)
    write('circuit.json',emit(expressions));write('audit.json',original)
    native=out/'native';native.mkdir()
    # Worker paths stay relative to its working directory, including saved metadata.
    config=dict(Mode='adaptive',Output='.',MaxDepth=1,WholeDepth=max_depth or 0,
                InputBits=p.n,OutputBits=p.m,Costs=p.costs,SBox=p.sbox,Initial=expressions,
                MaxStates=max_states,MaxDemands=max_demands,Seconds=seconds,SliceSeconds=slice_seconds,
                Threads=1,CacheEntries=8,StopAfterFirst=stop_after_first)
    config.update(AdaptiveFeedback=feedback,AdaptiveCovers=covers,AdaptiveRefresh=refresh,
                  DecisionLogMaxBytes=decision_log_max_bytes)
    write('native/config.json',config)
    with (out/'native.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([pwsh,'-NoProfile','-File',str(Path(__file__).resolve().parent/'native'/'run.ps1'),'-Config','config.json'],cwd=native.resolve(),stdout=log,stderr=subprocess.STDOUT)
        try:code=process.wait()
        except KeyboardInterrupt:
            (native/'STOP').write_text('stop\n',encoding='utf-8')
            try:code=process.wait(timeout=15)
            except (KeyboardInterrupt,subprocess.TimeoutExpired):process.terminate();process.wait();code=2
    if not (native/'adaptive.json').exists():raise RuntimeError('Adaptive worker did not finish; inspect native.log')
    report=json.loads((native/'adaptive.json').read_text(encoding='utf-8-sig'))
    found=json.loads((native/'best.json').read_text(encoding='utf-8-sig'))
    audit(p,found,partial=True)
    by={r['out']:r for r in found['gates']};memo={}
    def expr(n):
        if n in p.inputs:return n
        if n not in memo:
            r=by[n];memo[n]=[r['type'],*[expr(a) for a in r['in']]]
        return memo[n]
    for y,n in found['outputs'].items():
        j=int(y[1:]);e=expr(n)
        if max_depth is not None and expression_depth(e)>max_depth:raise ValueError('Adaptive worker exceeded the depth limit')
        if j not in expressions or p.expression(e)[1]<p.expression(expressions[j])[1]:expressions[j]=e
    report.update(engine='adaptive',max_depth=max_depth,initial_upper_bound_fs=original['worst_fs'] if original['all_outputs_found'] else None,
                  optimal_within_depth=False,global_optimality_proved=False,worker_exit_code=code)
    return report,expressions
