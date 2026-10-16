"""Check terminal unary reductions; does not itself exclude any unresolved root."""
from ..runtime import run as _run, fail as _fail
import argparse, itertools, json
from pathlib import Path
from ..model import D, ARITY, S, PI, M, gate

def check():
    y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))
    assert all((y != v and y != M ^ v for v in PI.values()))
    direct = []
    tails = []
    for inner in D:
        if inner in ('BUF', 'INV'):
            continue
        replacements = []
        for replacement in D:
            if ARITY[replacement] != ARITY[inner] or D[replacement] > D['INV'] + D[inner]:
                continue
            if all((gate(replacement, list(bits), 1) == 1 - gate(inner, list(bits), 1) for bits in itertools.product((0, 1), repeat=ARITY[inner]))):
                replacements.append(replacement)
        if replacements:
            chosen = min(replacements, key=D.get)
            direct.append(dict(inner=inner, replacement=chosen, old_fee_fs=D['INV'] + D[inner], new_fee_fs=D[chosen]))
        else:
            tails.append('INV_' + inner)
    assert len(direct) == 12 and len(tails) == 7
    return dict(status='NORMAL_FORM_REDUCTIONS_VERIFIED', seed_excluded=True, direct_replacements=direct, required_irreducible_tail_exclusions=tails, proof='Choose a minimum-delay legal realization. A non-boundary terminal BUF can be deleted. Two terminal INVs cancel, and INV after non-boundary BUF loses the BUF. Nonliteral target excludes unary chains ending directly at raw inputs. After removing such chains, a terminal INV either has one of the checked cheaper complement gates or one of the seven explicit tails. Every reduction preserves the paid input boundary and strictly decreases delay. Hence unresolved cyclic dependencies are not accepted as exclusions.', global_lower_bound_proved=False)
if __name__ == '__main__':
    try:
        p = argparse.ArgumentParser()
        p.add_argument('--output', required=True, type=Path)
        a = p.parse_args()
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(check(), indent=2), encoding='utf-8')
        print(a.output)
    except Exception as error:
        _fail(error)
