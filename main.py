"""Minimal entry points for the shared search and construction cores."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = 'ches2027'

from .core.model import Problem, emit
from .search.fixed.audit import audit
from .search.common.settings import configured_path

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text())


def timing(policy, profile, config):
    if policy == 'nldm':
        from .search.nldm.search import make_timing
    elif policy == 'practice':
        from .search.practice.search import make_timing
    else:
        raise ValueError('Unknown timing policy')
    return make_timing(profile, config)


def main():
    config, profiles = load('config.json'), load('profiles.json')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['search', 'verify', 'construct', 'proof'], nargs='?', default='search')
    parser.add_argument('--technology', type=int, choices=[15, 45, 55])
    parser.add_argument('--policy', choices=['fixed', 'nldm', 'practice', 'sta'],
                        help='Timing policy; sta is an alias for practice')
    parser.add_argument('--bits', type=int, choices=[4, 5, 6], default=4)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--proof-stage', choices=['plan', 'check', 'run', 'audit'], default='plan')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.resume and (args.task != 'proof' or args.proof_stage != 'run'):
        parser.error('--resume applies to proof --proof-stage run')
    if args.config:
        config = json.loads(configured_path(args.config).read_text())
    args.technology = args.technology or config['technology_nm']
    if args.seconds is not None and args.seconds <= 0:
        parser.error('--seconds must be positive')
    profile = profiles[str(args.technology)]
    problem = Problem.load(ROOT / 'examples' / 'apn6.json')
    problem.costs = profile['gate_costs_fs']
    if args.task == 'proof':
        if args.technology != 45 or args.policy not in (None, 'fixed'):
            raise ValueError('The APN6 proof uses the specified 45 nm fixed-cost model')
        from .search.fixed.proof.model import D, S
        if problem.costs != D or problem.sbox != S:
            raise ValueError('The proof requires the supplied APN6 mapping and gate costs')
        from .search.fixed.proof.entry import execute
        result = execute(args.proof_stage, configured_path(args.output or config['output']), args.resume)
        print(json.dumps(result, indent=2))
        return
    if args.task == 'verify':
        result = audit(problem, load('examples/apn6_witness.json'))
        if args.technology == 45 and result['worst_fs'] != config['expected_fixed_delay_fs']:
            raise ValueError('APN6 reference delay mismatch')
        print(json.dumps(dict(task='verify', technology_nm=args.technology,
                              delay_ps=result['worst_fs'] / 1000, audit=result), indent=2))
        return
    policy = args.policy or (config['construction']['timing'] if args.task == 'construct' else config['policy'])
    if policy == 'sta':
        policy = 'practice'
    out = configured_path(args.output or config['output'])
    out.mkdir(parents=True, exist_ok=False)
    if args.task == 'search' and policy == 'fixed':
        from .search.fixed.adaptive import search
        report, expressions = search(problem, out,
            seconds=args.seconds or config['search_seconds'], max_states=config['max_states'],
            max_demands=config['max_demands'], slice_seconds=config['native_slice_seconds'],
            decision_log_max_bytes=0)
        circuit = emit(expressions)
        result = audit(problem, circuit, partial=True)
        (out / 'circuit.json').write_text(json.dumps(circuit, indent=2) + '\n')
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    elif policy == 'fixed':
        raise ValueError('Construction uses practice by default or optional NLDM timing')
    else:
        if args.task == 'search':
            if policy == 'nldm':
                from .search.nldm.search import create_search
            elif policy == 'practice':
                from .search.practice.search import create_search
            else:
                raise ValueError('Unknown timing policy')
            engine = create_search(problem, profile, config, args.seconds)
            result = engine.run()
            (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
            if all(i is not None for i in engine.roots):
                (out / 'circuit.json').write_text(json.dumps(engine.structures.circuit(engine.roots), indent=2) + '\n')
        else:
            measure, library, paths = timing(policy, profile, config)
            from .construction.pool import Pool
            from .construction.assemble import construct
            settings = dict(config['construction'], **config['construction']['targets'][str(args.bits)])
            pool_time = args.seconds / 3 if args.seconds else settings['pool_seconds']
            assembly_time = args.seconds * 2 / 3 if args.seconds else settings['assembly_seconds']
            pool = Pool(args.bits, profile['gate_costs_fs'], measure, paths,
                        settings['depth'], settings['variants_per_function'], config['load_ff'])
            pool.generate(pool_time)
            pool.save(out / 'pool.json')
            candidates = construct(pool, settings, assembly_time)
            result = dict(status='FEASIBLE' if candidates else 'NO_CANDIDATES', candidates=candidates)
            (out / 'candidates.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted', file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        # Configuration failures should not print local installation paths.
        print(type(error).__name__ + ': configuration or backend failure', file=sys.stderr)
        sys.exit(1)
