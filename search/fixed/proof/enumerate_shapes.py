"""Phase 1: enumerate structures only, without truth tables or variable labels."""
from .runtime import run as _run, fail as _fail
import argparse, json, time, hashlib
from pathlib import Path
from .count_shapes import report
from .structures import unrank, metrics, root_ranges, global_rank

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bound-fs', type=int, default=157297)
    p.add_argument('--root', choices=list(__import__('model').D))
    p.add_argument('--raw', action='store_true', help='Retain removable BUF/INV structures')
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--limit', type=int, required=True, help='Explicit structure block size; no hidden truncation')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert a.start >= 0 and a.limit > 0
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    start = time.time()
    ranges = root_ranges(a.bound_fs, not a.raw, a.root)
    total = sum((n for _, n in ranges))
    assert a.start <= total
    end = min(total, a.start + a.limit)
    r = report(a.bound_fs, not a.raw)
    r.update(root_filter=a.root, selected_shapes=str(total), start=str(a.start), end=str(end))
    (out / 'count.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    digest = hashlib.sha256()
    with (out / 'shapes.jsonl').open('wb') as f:
        for index in range(a.start, end):
            rank = global_rank(ranges, index)
            shape = unrank(a.bound_fs, rank, not a.raw)
            delay, leaves, gates = metrics(shape)
            assert delay <= a.bound_fs
            line = (json.dumps(dict(index=str(index), global_rank=str(rank), shape=shape, delay_fs=delay, leaves=leaves, gates=gates), separators=(',', ':')) + '\n').encode()
            f.write(line)
            digest.update(line)
    status = dict(status='STRUCTURE_BLOCK_COMPLETE', bound_fs=a.bound_fs, normal_form=not a.raw, root_filter=a.root, total_shapes=str(total), start=str(a.start), end=str(end), emitted=end - a.start, all_selected_structures_emitted=a.start == 0 and end == total, sha256=digest.hexdigest(), seconds=time.time() - start, global_lower_bound_proved=False)
    (out / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    print(json.dumps(status, indent=2))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
