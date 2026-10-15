"""Minimal entry points for the shared search and construction cores."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = 'ches2027'

from .core.model import Problem, emit
from .search.fixed.audit import audit

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text())


def configured_path(value):
    if 'the/path/of/' in str(value):
        raise ValueError('Replace the/path/of/xxx with a configured location')
    return Path(value)


def timing(policy, profile, config):
    from .timing.library import read_library
    from .timing.oracle import NLDM
    path = configured_path(profile['liberty'])
    library = read_library(path)
    if policy == 'nldm':
        return NLDM(library, config['slew_ps']), library, None
    from .timing.sta import MappedSTA
    from .timing.path_score import PathTable
    for token in config['eda_command']:
        if 'the/path/of/' in token:
            raise ValueError('Configure the external EDA adapter command')
    measure = MappedSTA(config['eda_command'], path, config['slew_ps'])
    paths = PathTable(measure, config['path_depth'], config['path_budget'], config['load_ff'])
    return measure, library, paths


def main():
    config, profiles = load('config.json'), load('profiles.json')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['search', 'verify', 'construct'], nargs='?', default='search')
    parser.add_argument('--technology', type=int, choices=[15, 45, 55])
    parser.add_argument('--policy', choices=['fixed', 'nldm', 'sta'])
    parser.add_argument('--bits', type=int, choices=[4, 5, 6], default=4)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    if args.config:
        config = json.loads(configured_path(args.config).read_text())
    args.technology = args.technology or config['technology_nm']
    if args.seconds is not None and args.seconds <= 0:
        parser.error('--seconds must be positive')
    profile = profiles[str(args.technology)]
    problem = Problem.load(ROOT / 'examples' / 'apn6.json')
    problem.costs = profile['gate_costs_fs']
    if args.task == 'verify':
        result = audit(problem, load('examples/apn6_witness.json'))
        if args.technology == 45 and result['worst_fs'] != config['expected_fixed_delay_fs']:
            raise ValueError('APN6 reference delay mismatch')
        print(json.dumps(dict(task='verify', technology_nm=args.technology,
                              delay_ps=result['worst_fs'] / 1000, audit=result), indent=2))
        return
    policy = args.policy or (config['construction']['timing'] if args.task == 'construct' else config['policy'])
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
        raise ValueError('Construction uses STA by default or optional NLDM timing')
    else:
        measure, library, paths = timing(policy, profile, config)
        if args.task == 'search':
            from .search.bidirectional import Search, Config
            from .timing.oracle import Oracle
            cfg = Config(seconds=args.seconds or config['search_seconds'],
                         max_states=config['max_states'], max_demands=config['max_demands'],
                         timing='measured' if policy == 'sta' else 'nldm')
            factory = lambda s: Oracle(s, measure, library, paths, config['load_ff'])
            engine = Search(problem, factory, cfg)
            result = engine.run()
            (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
            if all(i is not None for i in engine.roots):
                (out / 'circuit.json').write_text(json.dumps(engine.structures.circuit(engine.roots), indent=2) + '\n')
        else:
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
