"""Fresh complete zero-cover bases, with optional final NAND/AND root proof.

OAI21 mode generates centers only; its inner-function proof remains separate.
"""
from ...runtime import run as _run, fail as _fail
from pathlib import Path
import argparse, itertools, json, os, shutil, struct, subprocess, sys
HERE = Path(__file__).resolve().parent
from ...model import D, M, S, maximal
from ...family_checks.library import build, quote
CUT = 157297 - D['OAI21']
Y = sum(((value >> 2 & 1) << x for x, value in enumerate(S)))
Z = M ^ Y

def dump(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')

def read_image(path):
    with path.open('rb') as stream:
        found, count = struct.unpack('<II', stream.read(8))
        assert found == 0
        for _ in range(count):
            yield struct.unpack('<Qiiiiii', stream.read(32))
        assert not stream.read(1)

def write_inputs(path, rows):
    with path.open('wb') as stream:
        stream.write(struct.pack('<I', len(rows)))
        for f, t in rows:
            stream.write(struct.pack('<QI', f, t))

def native(out, name, source, arguments, pwsh):
    script = out / (name + '.ps1')
    script.write_text("$ErrorActionPreference='Stop'\nAdd-Type -Path " + quote(source) + '\n[' + source.stem + ']::Run(' + ','.join(arguments) + ')\n', encoding='utf-8')
    with (out / (name + '.log')).open('w', encoding='utf-8') as log:
        _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})

def records(path, fmt):
    width = struct.calcsize(fmt)
    with path.open('rb') as stream:
        count, = struct.unpack('<I', stream.read(4))
        for _ in range(count):
            yield struct.unpack(fmt, stream.read(width))
        assert not stream.read(1)

def main():
    global CUT, Y, Z
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--root', choices=['OAI21', 'NAND3', 'NAND4', 'AND2', 'AND3'], default='OAI21')
    args = parser.parse_args()
    CUT = 157297 - D[args.root]
    if args.root.startswith('AND'):
        Y = M ^ Y
    Z = M ^ Y
    pwsh = shutil.which('pwsh')
    if not pwsh:
        raise SystemExit('PowerShell 7 is required')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    status = dict(status='INCOMPLETE', phase='building_fresh_library', root=args.root, root_deadline_fs=157297, child_deadline_fs=CUT, previous_result_files_read=0)
    dump(out / 'status.json', status)
    library = out / 'library'
    library.mkdir()
    image = build(CUT - min(D.values()), library, pwsh)

    def inputs(cut, mixed=False):
        values = {f: t for f, t, *_ in read_image(image) if t <= cut}
        if mixed:
            return [(key ^ Z, t) for key, t in maximal({f ^ Z: t for f, t in values.items()}).items()]
        return list(values.items())
    covers = {}

    def add(cover, arrival):
        assert cover & Z == 0 and arrival <= CUT
        if cover:
            covers[cover] = min(arrival, covers.get(cover, arrival))
    for f, t, *_ in read_image(image):
        if f & Z == Z:
            add(M ^ f, t)
        if (M ^ f) & Z == Z and t + D['INV'] <= CUT:
            add(f, t + D['INV'])
    for gate in ('NAND2', 'NAND4', 'OAI22', 'AOI22'):
        rows = inputs(CUT - D[gate], mixed=True)
        if gate in ('NAND4', 'OAI22'):
            pairs = {}
            for (a, ta), (b, tb) in itertools.combinations_with_replacement(rows, 2):
                value = a & b if gate == 'NAND4' else a | b
                key, t = (value ^ Z, max(ta, tb))
                pairs[key] = min(t, pairs.get(key, t))
            rows = [(key ^ Z, t) for key, t in maximal(pairs).items()]
        inp, result = (out / (gate + '.input'), out / (gate + '.result'))
        write_inputs(inp, rows)
        native(out, gate, HERE.parent / 'PairEngine.cs', [quote(inp), quote(result), "[UInt64]::Parse('" + str(Y) + "')"], pwsh)
        products = {}
        for cover, _, a, b in records(result, '<Qiii'):
            t = max(rows[a][1], rows[b][1])
            if gate == 'AOI22':
                products[cover] = min(t, products.get(cover, t))
            else:
                add(cover, t + D[gate])
        if gate == 'AOI22':
            products = list(maximal(products).items())
            for (a, ta), (b, tb) in itertools.combinations_with_replacement(products, 2):
                add(a | b, max(ta, tb) + D[gate])
    inp, result = (out / 'OAI21.input', out / 'OAI21.result')
    write_inputs(inp, inputs(CUT - D['OAI21'], mixed=True))
    native(out, 'OAI21', HERE / 'OaiEngine.cs', [quote(inp), quote(result), "[UInt64]::Parse('" + str(Y) + "')"], pwsh)
    for cover, t, *_ in records(result, '<Qiiii'):
        add(cover, t)
    inp, result = (out / 'remaining.input', out / 'remaining.result')
    write_inputs(inp, inputs(CUT - min(D.values())))
    native(out, 'remaining', HERE / 'RemainingImage.cs', [quote(inp), quote(result), str(CUT), "[UInt64]::Parse('" + str(Z) + "')"], pwsh)
    for f, t, *_ in read_image(result):
        add(M ^ f, t)
    known = out / 'known.bin'
    covers = maximal(covers)
    with known.open('wb') as stream:
        stream.write(struct.pack('<I', len(covers)))
        for cover in covers:
            stream.write(struct.pack('<Q', cover))
    inp, result = (out / 'NAND3.input', out / 'NAND3.result')
    write_inputs(inp, inputs(CUT - D['NAND3'], mixed=True))
    native(out, 'NAND3', HERE / 'Nand3CenterProof.cs', [quote(inp), quote(result), "[UInt64]::Parse('" + str(Y) + "')", quote(known)], pwsh)
    for cover, t, *_ in records(result, '<Qiiii'):
        add(cover, t)
    covers = maximal(covers)
    dump(out / 'centers.json', dict(center_deadline_fs=CUT, zero_covers=list(covers), count=len(covers)))
    if args.root != 'OAI21':
        from ...family_checks.root_cases.cover_certificate import emit, verify
        basis = out / 'basis.json'
        dump(basis, dict(target=Y, zero_masks=list(covers), child_deadline_fs=CUT))
        proof = out / 'cover_certificate'
        proof.mkdir()
        emit(basis, proof, int(args.root[-1]))
        verified = verify(proof)
        dump(proof / 'certificate.json', verified)
        status.update(status='ROOT_EXCLUDED', phase='FINISHED', root_result='UNSAT', centers=len(covers), cover_certificate=verified, global_lower_bound_proved=False)
        dump(out / 'status.json', status)
        print(json.dumps(status, indent=2))
        return 0
    status.update(phase='CENTER_GENERATION_FINISHED', centers=len(covers), missing_stages=['fresh_global_inner_domains_for_all_21_gates', 'complete_center_conditioned_two_cover_query'], proof_result='UNKNOWN')
    dump(out / 'status.json', status)
    print(json.dumps(status, indent=2))
    return 2
if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        _fail(error)
