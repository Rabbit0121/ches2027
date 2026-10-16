"""Independent per-structure Python comparison against the native union."""
from .runtime import run as _run, fail as _fail
import argparse, json, struct, time
from pathlib import Path
from .beam_truths import Engine
from .count_shapes import count
from .structures import unrank, metrics

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    start = time.time()
    bound = int(a.image.parent.name)
    oracle = {}
    engine = Engine()
    for i in range(count(bound, True)):
        s = unrank(bound, i, True)
        delay = metrics(s)[0]
        for f in engine.expand(s):
            oracle[f] = min(delay, oracle.get(f, delay))
    with a.image.open('rb') as f:
        found, n = struct.unpack('<II', f.read(8))
        assert not found
        native = {v: t for v, t, *_ in struct.iter_unpack('<Qiiiiii', f.read())}
    assert len(native) == n and native == oracle
    r = dict(status='PASS', bound_fs=bound, structures=count(bound, True), functions=n, comparison='Every truth table and its minimum arrival, independent Python per-structure expansion versus native engine', seconds=time.time() - start)
    a.output.write_text(json.dumps(r, indent=2), encoding='utf-8')
    print(json.dumps(r))
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
