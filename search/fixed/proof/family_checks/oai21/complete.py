from ...runtime import work_relative
from ...runtime import work_reference
"""Generate all OAI21 inner families and query exact common-center pairs.

Default execution first rebuilds centers. --center-run resumes from a complete
center-generation run made with this package; no archived evidence is read.
Every symbolic intermediate has the common leaf deadline, not a charged gate.
"""
from ...runtime import run as _run, fail as _fail
import argparse, json, os, shutil, struct, subprocess, sys, time
from pathlib import Path
H = Path(__file__).resolve().parent
P = H.parent
from ...model import D, M, S
from ...family_checks.library import quote
from ...family_checks.oai21.centers import read_image, write_inputs, records
Y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
Z = M ^ Y
CUT = 157297 - D['OAI21']

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--center-run', type=Path)
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pwsh = shutil.which('pwsh')
    assert pwsh
    start = time.time()
    report = dict(status='RUNNING', root='OAI21', root_deadline_fs=157297, child_deadline_fs=CUT, global_lower_bound_proved=False)

    def save():
        (out / 'status.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    cr = a.center_run.resolve() if a.center_run else out / 'center_run'
    if not a.center_run:
        cp = _run([sys.executable, str(H / 'centers.py'), '--output', str(cr)])
        assert cp.returncode in (0, 2)
    status = json.loads((cr / 'status.json').read_bytes())
    data = json.loads((cr / 'centers.json').read_bytes())
    assert status['phase'] == 'CENTER_GENERATION_FINISHED' and data['center_deadline_fs'] == CUT
    cs = data['zero_covers']
    assert len(cs) == data['count'] and all((c & Z == 0 for c in cs))
    centers = out / 'centers.bin'
    with centers.open('wb') as f:
        f.write(struct.pack('<I', len(cs)))
        for c in cs:
            f.write(struct.pack('<Q', c))
    allowed = set()
    for c in cs:
        q = c
        while True:
            allowed.add(q)
            if not q:
                break
            q = q - 1 & c
    image = cr / 'library' / str(CUT - min(D.values())) / 'image.bin'
    cert = json.loads((image.parent / 'certificate.json').read_bytes())
    assert cert['status'] == 'COMPLETE_FROM_PAID_SEEDS' and cert['bound_fs'] == 102598

    def native(name, types, command):
        script = out / (name + '.ps1')
        script.write_text("$ErrorActionPreference='Stop'\nAdd-Type -Path @(" + ','.join((quote(H / (t + '.cs')) for t in types)) + ')\n' + command + '\n', encoding='utf-8')
        with (out / (name + '.log')).open('w') as log:
            _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})

    def extract(name, cut, invert=False, compatible=False):
        p = out / (name + '.leaves')
        n = 0
        with p.open('wb') as f:
            f.write(struct.pack('<II', 0, 0))
            for v, t, *_ in read_image(image):
                if t > cut:
                    continue
                if invert:
                    v = M ^ v
                if compatible and v & Y not in allowed:
                    continue
                f.write(struct.pack('<Qiiiiii', v, t, -1, -1, -1, -1, -1))
                n += 1
            f.seek(4)
            f.write(struct.pack('<I', n))
        return p

    def reduce(name, source, header, stride, offset):
        manifest = out / (name + '.manifest')
        manifest.write_text(f'0\t{work_relative(source)}\t{header}\t{stride}\t{offset}\n', encoding='utf-8')
        dest = out / (name + '.max')
        audit = out / (name + '.audit')
        native(name + '_reduce', ['MixedMaxFast'], f"[MixedMaxFast]::Run({quote(manifest)},'',{quote(dest)},[UInt64]::Parse('{Y}'))\n[MixedMaxFast]::Verify({quote(manifest)},{quote(dest)},{quote(audit)},[UInt64]::Parse('{Y}'))")
        r = json.loads(Path(str(dest) + '.json').read_bytes())
        v = json.loads((audit / 'native.json').read_bytes())
        assert r['status'] == 'COMPLETE_EXACT_MIXED_MAXIMA' and v['status'] == 'ALL_SOURCE_ROWS_HAVE_EXPLICIT_DOMINATOR'
        return Path(str(dest) + '.truths')

    def truth_image(name, source, cut, group=-1):
        p = out / (name + '.image')
        with source.open('rb') as f, p.open('wb') as w:
            n, = struct.unpack('<I', f.read(4))
            w.write(struct.pack('<II', 0, n))
            for _ in range(n):
                v, = struct.unpack('<Q', f.read(8))
                w.write(struct.pack('<Qiiiiii', v, cut, group, -1, -1, -1, -1))
            assert not f.read(1)
        return p

    def pair(name, source, use_or):
        dest = out / (name + '.pairs')
        flag = '$true' if use_or else '$false'
        native(name, ['GlobalPairs'], f"[GlobalPairs]::Run({quote(centers)},{quote(source)},{quote(dest)},[UInt64]::Parse('{Y}'),{flag},$true)")
        r = json.loads(Path(str(dest) + '.json').read_bytes())
        assert r['status'] == 'COMPLETE_CENTER_COMPATIBLE_PAIRS'
        return dest
    blocks = []
    families = []

    def add(name, source, header, stride, offset):
        truths = reduce(name + '_final', source, header, stride, offset)
        blocks.append(truths)
        families.append(name)
        report.update(completed_families=families, center_count=len(cs), downset_count=len(allowed))
        save()
    inv = extract('INV', CUT - D['INV'], True, True)
    add('INV', inv, 8, 32, 4)
    for gate, invert, op in [('NAND2', True, True), ('AND2', False, False), ('NOR2', True, False)]:
        cut = CUT - D[gate]
        leaf = extract(gate, cut, invert, op)
        reduced = reduce(gate + '_leaves', leaf, 8, 32, 4)
        inp = truth_image(gate, reduced, cut)
        res = pair(gate, inp, op)
        add(gate, res, 4, 20, 0)
    for gate in ('NAND3', 'NAND4'):
        cut = CUT - D[gate]
        leaf = extract(gate, cut, True, True)
        reduced = reduce(gate + '_leaves', leaf, 8, 32, 4)
        if gate == 'NAND3':
            inp = out / 'NAND3.input'
            with reduced.open('rb') as f, inp.open('wb') as w:
                n, = struct.unpack('<I', f.read(4))
                w.write(struct.pack('<I', n))
                for _ in range(n):
                    v, = struct.unpack('<Q', f.read(8))
                    w.write(struct.pack('<QI', v, cut))
            res = out / 'NAND3.truths'
            native('NAND3', ['GlobalTriple'], f"[GlobalTriple]::Run({quote(centers)},{quote(inp)},{quote(res)},[UInt64]::Parse('{Y}'))")
            r = json.loads(Path(str(res) + '.json').read_bytes())
            assert r['status'] == 'COMPLETE_COMMON_CENTER_NAND3_TRUTHS'
            add(gate, res, 4, 8, 0)
        else:
            inp = truth_image(gate + '_leaves', reduced, cut)
            symbolic = pair('NAND4_symbolic', inp, True)
            sp = reduce('NAND4_symbolic', symbolic, 4, 20, 0)
            inp = truth_image('NAND4_symbolic', sp, cut)
            res = pair(gate, inp, True)
            add(gate, res, 4, 20, 0)
    cut = CUT - D['OAI21']
    leaf = extract('OAI21_all', cut, True, False)
    reduced = reduce('OAI21_all_leaves', leaf, 8, 32, 4)
    inp = truth_image('OAI21_all', reduced, cut)
    products = pair('OAI21_products', inp, False)
    pr = reduce('OAI21_products', products, 4, 20, 0)
    wr = reduce('OAI21_W', extract('OAI21_W', cut, True, True), 8, 32, 4)
    assert any((f == M and t <= cut for f, t, *_ in read_image(image)))
    blocks.extend([pr, wr])
    families.extend(['OAI21_P_identity', 'OAI21_W_identity'])
    cross = out / 'OAI21.cross'
    n = 0
    with cross.open('wb') as w:
        w.write(struct.pack('<II', 0, 0))
        for source, group in ((pr, -1), (wr, -2)):
            with source.open('rb') as f:
                count, = struct.unpack('<I', f.read(4))
                n += count
                for _ in range(count):
                    v, = struct.unpack('<Q', f.read(8))
                    w.write(struct.pack('<Qiiiiii', v, cut, group, -1, -1, -1, -1))
        w.seek(4)
        w.write(struct.pack('<I', n))
    res = out / 'OAI21.pairs'
    native('OAI21', ['GlobalCross'], f"[GlobalCross]::Run({quote(centers)},{quote(cross)},{quote(res)},[UInt64]::Parse('{Y}'),$true,$true)")
    r = json.loads(Path(str(res) + '.json').read_bytes())
    assert r['status'] == 'COMPLETE_CENTER_COMPATIBLE_CROSS_PAIRS'
    add('OAI21', res, 4, 20, 0)
    for name, engine, cut in [('cheap11', 'GlobalCheapFull', CUT - D['BUF']), ('aoi3', 'GlobalAoiFull', CUT - D['AOI21'])]:
        inp = out / (name + '.input')
        write_inputs(inp, [(f, t) for f, t, *_ in read_image(image) if t <= cut])
        res = out / (name + '.image')
        native(name, [engine], f"[{engine}]::Run({quote(inp)},{quote(res)},{CUT},[UInt64]::Parse('{Y}'),{quote(centers)})")
        r = json.loads(Path(str(res) + '.status.json').read_bytes())
        assert not r['found'] and r['bound'] == CUT
        add(name, res, 8, 32, 4)
    merged = out / 'all_inner.truths'
    n = 0
    with merged.open('wb') as w:
        w.write(struct.pack('<I', 0))
        for p in blocks:
            with p.open('rb') as f:
                count, = struct.unpack('<I', f.read(4))
                n += count
                shutil.copyfileobj(f, w)
        w.seek(0)
        w.write(struct.pack('<I', n))
    result = out / 'final_query.json'
    native('final_query', ['OaiFinalCover'], f"[OaiFinalCover]::Run({quote(centers)},{quote(merged)},{quote(result)},[UInt64]::Parse('{Y}'),0)")
    r = json.loads(result.read_bytes())
    assert r['status'] == 'COMPLETE_NO_COMMON_CENTER_TWO_COVER', r['status']
    report.update(status='ROOT_EXCLUDED', root_result='UNSAT', completed_families=families, final_query=r, center_source=work_reference(cr), seconds=time.time() - start)
    save()
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
