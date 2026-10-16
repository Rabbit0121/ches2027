"""Rebuild the NOR2 and AOI21 exclusions from a fresh complete lower domain."""
from ...runtime import run as _run, fail as _fail
import argparse, json, os, shutil, struct, subprocess, sys, time
from pathlib import Path
H = Path(__file__).resolve().parent
from ...model import D, M, S, maximal
from ...family_checks.library import build, quote
from ...family_checks.root_cases.cover_certificate import emit, verify

def read_image(p):
    with p.open('rb') as f:
        found, n = struct.unpack('<II', f.read(8))
        assert found == 0
        for _ in range(n):
            yield struct.unpack('<Qiiiiii', f.read(32))
        assert not f.read(1)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--root', required=True, choices=['NOR2', 'AOI21'])
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pwsh = shutil.which('pwsh')
    assert pwsh
    Y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    cut = 157297 - D[a.root]
    start = time.time()
    status = dict(status='RUNNING', root=a.root, root_deadline_fs=157297, child_deadline_fs=cut, global_lower_bound_proved=False)

    def save():
        (out / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    save()
    lib = out / 'fresh_library'
    lib.mkdir()
    image = build(cut - min(D.values()), lib, pwsh)
    inp = out / 'input.bin'
    n = 0
    with inp.open('wb') as f:
        f.write(struct.pack('<I', 0))
        for truth, t, *_ in read_image(image):
            f.write(struct.pack('<QI', truth, t))
            n += 1
        f.seek(0)
        f.write(struct.pack('<I', n))

    def native(name, sources, command):
        script = out / (name + '.ps1')
        script.write_text("$ErrorActionPreference='Stop'\nAdd-Type -Path @(" + ','.join(map(quote, sources)) + ')\n' + command + '\n', encoding='utf-8')
        with (out / (name + '.log')).open('w') as log:
            _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    children = out / 'children.bin'
    native('children', [H / 'CSubsetImage.cs'], f"[CSubsetImage]::Run({quote(inp)},{quote(children)},{cut},[UInt64]::Parse('{Y}'))")
    rows = {f: row for f, *row in read_image(children)}
    assert all((f & Y == 0 and row[0] <= cut for f, row in rows.items()))
    kept = maximal(rows)
    status.update(compatible_children=len(rows), maximal_children=len(kept))
    save()
    if a.root == 'NOR2':
        basis = out / 'basis.json'
        basis.write_text(json.dumps(dict(target=M ^ Y, zero_masks=list(kept), child_deadline_fs=cut, mask_meaning='Actual one sets, not zero sets')), encoding='utf-8')
        cert = out / 'cover_certificate'
        cert.mkdir()
        emit(basis, cert, 2)
        verified = verify(cert)
        (cert / 'certificate.json').write_text(json.dumps(verified, indent=2), encoding='utf-8')
        status.update(status='ROOT_EXCLUDED', root_result='UNSAT', cover_certificate=verified)
    else:
        centers = out / 'centers.bin'
        with centers.open('wb') as f:
            f.write(struct.pack('<I', len(kept)))
            for truth, row in kept.items():
                f.write(struct.pack('<Qiiiiii', truth, *row))
        result = out / 'stream.json'
        native('stream', [H / 'Aoi21Stream.cs'], f"[Aoi21Stream]::Run({quote(inp)},{quote(centers)},{quote(result)},{cut},[UInt64]::Parse('{Y}'),[double]::PositiveInfinity,[int]::MaxValue)")
        r = json.loads(result.read_bytes())
        assert r['bound'] == cut
        assert r['status'] == 'COMPLETE_NO_AOI21_AT_BOUND', r['status']
        checked = 0
        with Path(str(result) + '.projections.bin').open('rb') as f:
            nr, = struct.unpack('<I', f.read(4))
            assert nr == len(kept)
            for _ in range(nr):
                residual, m = struct.unpack('<QI', f.read(12))
                v = [struct.unpack('<Q', f.read(8))[0] for _ in range(m)]
                assert residual and all((x & ~Y == 0 for x in v))
                for i, x in enumerate(v):
                    assert all((x & y for y in v[i:]))
                checked += m
            assert not f.read(1)
        status.update(status='ROOT_EXCLUDED', root_result='UNSAT', native=r, checked_projections=checked)
    status.update(seconds=time.time() - start, previous_result_files_read=0)
    save()
    print(json.dumps(status, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
