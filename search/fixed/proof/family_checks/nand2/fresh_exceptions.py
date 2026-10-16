"""Generate the NAND3 heavy-cover sublemma from paid seeds. Not a NAND2 proof."""
from ...runtime import run as _run, fail as _fail
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
HERE = Path(__file__).resolve().parent
from ...model import D, M, S
from ...family_checks.library import build, quote
from ...family_checks.audit_library import audit
WEIGHTS = [0, 2202, 0, 1002, 833, 0, 6389, 0, 0, 0, 5303, 2008, 0, 8235, 0, 0, 0, 5497, 0, 0, 0, 0, 0, 10019, 9651, 0, 0, 6499, 0, 0, 0, 0, 369, 0, 3150, 0, 0, 3511, 0, 4605, 5158, 0, 0, 0, 3077, 0, 3574, 3511, 2008, 0, 1303, 7342, 1423, 1090, 2008, 0, 0, 7479, 4131, 0, 936, 1643, 0, 1741]
Y = sum(((v >> 2 & 1) << i for i, v in enumerate(S)))
Z = M ^ Y
THRESHOLD = sum(WEIGHTS) // 2 + 1

def read_rows(path):
    with path.open('rb') as f:
        n, = struct.unpack('<I', f.read(4))
        rows = [struct.unpack('<QI', f.read(12)) for _ in range(n)]
        assert not f.read(1)
    return rows

def weight(f):
    return sum((w for i, w in enumerate(WEIGHTS) if f >> i & 1))

def verify_dominance(original, kept, deadline):
    """Explicit dominating representative for every eligible original input."""
    positive = sum((1 << i for i, w in enumerate(WEIGHTS) if w))
    active = positive | Z
    known = dict(original)
    assert all((known.get(f) == t and t <= deadline for f, t in kept))
    posts = [0] * 64
    for j, (f, _) in enumerate(kept):
        v = (f ^ Z) & active
        while v:
            bit = v & -v
            posts[bit.bit_length() - 1] |= 1 << j
            v ^= bit
    order = sorted((b for b in range(64) if active >> b & 1), key=lambda b: posts[b].bit_count())
    checked = 0
    for f, _ in original:
        if weight(f) < THRESHOLD:
            continue
        possible = (1 << len(kept)) - 1
        key = (f ^ Z) & active
        for b in order:
            if key >> b & 1:
                possible &= posts[b]
        assert possible, 'No dominating legal input; reduction incomplete'
        g, _ = kept[(possible & -possible).bit_length() - 1]
        assert not f & positive & ~g and (not g & Z & ~f)
        checked += 1
    return checked

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    pwsh = shutil.which('pwsh')
    if not pwsh:
        raise SystemExit('PowerShell 7 required')
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'INCOMPLETE', 'nand2_root_proved': False, 'missing': ['Other child-root weighted bounds', 'All exceptional residual counterpart exclusions']}

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    assert all((w >= 0 and (not w or Y >> i & 1) for i, w in enumerate(WEIGHTS)))
    child_deadline = 157297 - D['NAND2']
    leaf_deadline = child_deadline - D['NAND3']
    domain = out / 'fresh_library'
    domain.mkdir()
    image = build(leaf_deadline, domain, pwsh)
    audits = [audit(p) for p in sorted(domain.iterdir()) if p.is_dir() and p.name.isdigit()]
    inputs = out / 'inputs.bin'
    with image.open('rb') as src, inputs.open('wb') as dst:
        found, count = struct.unpack('<II', src.read(8))
        assert found == 0
        dst.write(struct.pack('<I', count))
        for _ in range(count):
            f, t, *_ = struct.unpack('<Qiiiiii', src.read(32))
            assert t <= leaf_deadline
            dst.write(struct.pack('<QI', f, t))
        assert not src.read(1)
    weights = out / 'weights.bin'
    weights.write_bytes(struct.pack('<64i', *WEIGHTS))
    reduced = out / 'reduced.bin'
    exceptions = out / 'exceptions.bin'
    script = out / 'enumerate.ps1'
    script.write_text(f"$ErrorActionPreference='Stop'\nAdd-Type -Path {quote(HERE / 'WeightedInputMax.cs')}\nAdd-Type -Path {quote(HERE / 'PartitionedWeightedTripleJoin.cs')}\n[WeightedInputMax]::Run({quote(inputs)},{quote(weights)},{quote(reduced)},[UInt64]::Parse('{Y}'),{THRESHOLD})\n$env:NAND3_WEIGHTS_PATH={quote(weights)}\n$env:NAND3_STOP_FIRST='0'\n$env:NAND3_START_TASK='0'\n$env:NAND3_FRONTIER_SIZE='8192'\n[PartitionedWeightedTripleJoin]::Run({quote(reduced)},{quote(exceptions)},[UInt64]::Parse('{Y}'),{THRESHOLD},0)\n", encoding='utf-8')
    with (out / 'native.log').open('w') as log:
        _run([pwsh, '-NoProfile', '-File', str(script)], check=True, stdout=log, stderr=subprocess.STDOUT, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
    original, kept = (read_rows(inputs), read_rows(reduced))
    checked = verify_dominance(original, kept, leaf_deadline)
    native = json.loads(Path(str(exceptions) + '.json').read_bytes())
    tasks = json.loads(Path(str(exceptions) + '.tasks.json').read_bytes())
    assert native['status'] == 'COMPLETE'
    assert tasks['start_task'] == 0 and tasks['next_task'] == tasks['total_tasks']
    zero = Y & ~sum((1 << i for i, w in enumerate(WEIGHTS) if w))
    terms = []
    with exceptions.open('rb') as f:
        count, = struct.unpack('<I', f.read(4))
        for _ in range(count):
            cover, arrival, i, j, k = struct.unpack('<Qiiii', f.read(24))
            assert cover == kept[i][0] & kept[j][0] & kept[k][0]
            assert arrival == max((kept[q][1] for q in (i, j, k))) + D['NAND3'] <= child_deadline
            assert not cover & Z and weight(cover) >= THRESHOLD
            virtual = cover | zero
            terms.append(dict(cover=cover, weight=weight(cover), virtual_upper_cover=virtual, residual=Y & ~virtual))
        assert not f.read(1)
    assert len(terms) == native['covers']
    report.update(sublemma_status='COMPLETE_HEAVY_NAND3_COVER_ENUMERATION', leaf_deadline_fs=leaf_deadline, child_deadline_fs=child_deadline, weight_total=sum(WEIGHTS), threshold=THRESHOLD, complete_inputs=len(original), dominant_inputs=len(kept), checked_dominance_pairs=checked, completed_tasks=tasks['total_tasks'], exceptions=terms, library_witness_audits=audits, note='Complete sublemma only; status remains INCOMPLETE for the NAND2 root.')
    save()
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
