from .runtime import work_reference
"""Phase 2: assign variables to already enumerated structures and compare Y2.

Assignment orbits use only automorphisms of that fixed typed structure. No
global function library or truth-table equivalence between structures is used.
Progress records the next assignment exactly; PARTIAL is never a proof.
"""
from .runtime import run as _run, fail as _fail
import argparse, json, time, hashlib
from pathlib import Path
from .model import S, expression
from .structures import freeze, metrics, assignment_count, evaluate, instantiate
from .structures import root_ranges, global_rank, unrank
from .structural_filters import characteristics, rejection
from .input_partitions import partition_count, partition_unrank, target_orbit, evaluate_labels, instantiate_labels
Y = sum(((v >> 2 & 1) << x for x, v in enumerate(S)))

def support(f):
    return sum((any(((f >> x ^ f >> (x ^ 1 << i)) & 1 for x in range(64))) for i in range(6)))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalogue', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=float, default=0, help='0 means no time limit; a limit returns PARTIAL')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--no-structural-filters', action='store_true')
    p.add_argument('--backend', choices=('labels', 'beam'), default='labels')
    p.add_argument('--max-functions', type=int, default=0, help='Explicit per-table cap for beam backend; a limit returns PARTIAL')
    a = p.parse_args()
    out = a.output.resolve()
    cat = a.catalogue.resolve()
    meta = json.loads((cat / 'status.json').read_bytes())
    raw = (cat / 'shapes.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta['sha256']
    data = [json.loads(line) for line in raw.splitlines()]
    assert len(data) == meta['emitted']
    ranges = root_ranges(meta['bound_fs'], meta['normal_form'], meta['root_filter'])
    domain = sum((n for _, n in ranges))
    begin = int(meta['start'])
    end = int(meta['end'])
    assert str(domain) == meta['total_shapes'] and len(data) == end - begin and (0 <= begin <= end <= domain)
    assert meta['all_selected_structures_emitted'] == (begin == 0 and end == domain)
    for j, item in enumerate(data, begin):
        rank = global_rank(ranges, j)
        assert int(item['index']) == j and int(item['global_rank']) == rank
        assert freeze(item['shape']) == unrank(meta['bound_fs'], rank, meta['normal_form'])
    path = out / 'status.json'
    start = time.time()
    last_save = start
    if a.resume:
        r = json.loads(path.read_bytes())
        assert r['status'] == 'PARTIAL' and r['catalogue_sha256'] == meta['sha256']
        assert r['target_y2'] == Y and r['catalogue'] == str(cat)
        assert r['structural_filters'] == (not a.no_structural_filters)
        assert r['input_strategy'] == 'min_pin_orbits_and_variable_partitions_v1'
        assert r.get('backend', 'labels') == a.backend
    else:
        out.mkdir(parents=True, exist_ok=False)
        r = dict(status='PARTIAL', catalogue=work_reference(cat), catalogue_sha256=meta['sha256'], target_y2=Y, next_row=0, next_assignment='0', completed_structures=0, support_pruned_structures=0, structural_filters=not a.no_structural_filters, pruning_reasons={}, input_strategy='min_pin_orbits_and_variable_partitions_v1', backend=a.backend, beam_compositions=0, tested_assignments='0', elapsed_seconds=0, global_lower_bound_proved=False)
    prior_seconds = r['elapsed_seconds']
    tested = int(r['tested_assignments'])
    target = characteristics(Y, 6)
    assert target['support'] == 6
    orbit = target_orbit(Y)
    r['target_variable_orbit_size'] = len(orbit)
    if a.backend == 'beam':
        from .beam_truths import Engine, ExpansionLimit
        engine = Engine(max_functions=a.max_functions)
        previous_compositions = r.get('beam_compositions', 0)

    def save():
        r.update(tested_assignments=str(tested), elapsed_seconds=prior_seconds + time.time() - start)
        if a.backend == 'beam':
            r['beam_compositions'] = previous_compositions + engine.compositions
        temp = out / 'status.tmp'
        temp.write_text(json.dumps(r, indent=2), encoding='utf-8')
        temp.replace(path)
    try:
        while r['next_row'] < len(data):
            item = data[r['next_row']]
            s = freeze(item['shape'])
            delay, leaves, nodes = metrics(s)
            assert (delay, leaves, nodes) == (item['delay_fs'], item['leaves'], item['gates']) and delay <= meta['bound_fs']
            r['current_structure'] = item['index']
            reason = rejection(s, target) if not a.no_structural_filters else None
            if reason:
                r['support_pruned_structures'] += 1
                r['pruning_reasons'][reason] = r['pruning_reasons'].get(reason, 0) + 1
            elif a.backend == 'beam':
                try:
                    expr = engine.match(s, Y)
                except ExpansionLimit as error:
                    r['reason'] = str(error)
                    save()
                    print(json.dumps(r, indent=2))
                    return
                if expr is not None:
                    truth, arrival = expression(expr)
                    assert truth == Y and arrival == delay
                    r.update(status='FOUND_Y2', witness_expression=expr, witness_arrival_fs=arrival)
                    save()
                    print(json.dumps(r, indent=2))
                    return
            else:
                pins = assignment_count(s)
                partitions = partition_count(leaves)
                use_partitions = partitions < pins
                total = min(pins, partitions)
                index = int(r['next_assignment'])
                r['current_input_mode'] = 'variable_partitions' if use_partitions else 'pin_automorphisms'
                r['current_assignment_count'] = str(total)
                while index < total:
                    if use_partitions:
                        labels = partition_unrank(leaves, index)
                        value = evaluate_labels(s, labels)
                        hit = value in orbit
                    else:
                        value = evaluate(s, index)
                        hit = value == Y
                    tested += 1
                    if hit:
                        expr = instantiate_labels(s, [orbit[value][i] for i in labels]) if use_partitions else instantiate(s, index)
                        truth, arrival = expression(expr)
                        assert truth == Y and arrival == delay
                        r.update(status='FOUND_Y2', witness_expression=expr, witness_arrival_fs=arrival, witness_assignment=str(index))
                        save()
                        print(json.dumps(r, indent=2))
                        return
                    index += 1
                    r['next_assignment'] = str(index)
                    if tested % 2048 == 0:
                        now = time.time()
                        if now - last_save >= 5:
                            save()
                            last_save = now
                        if a.seconds and now - start >= a.seconds:
                            save()
                            print(json.dumps(r, indent=2))
                            return
            r['completed_structures'] += 1
            r['next_row'] += 1
            r['next_assignment'] = '0'
            if time.time() - last_save >= 5:
                save()
                last_save = time.time()
            if a.seconds and time.time() - start >= a.seconds:
                save()
                print(json.dumps(r, indent=2))
                return
        complete = meta['all_selected_structures_emitted']
        r['status'] = 'SELECTED_DOMAIN_EXCLUDED' if complete else 'BLOCK_EXCLUDED'
        r['all_selected_structures_checked'] = complete
        r['global_lower_bound_proved'] = complete and meta['root_filter'] is None and (meta['bound_fs'] == 157297)
        save()
        print(json.dumps(r, indent=2))
    except KeyboardInterrupt:
        save()
        print('PARTIAL: checkpoint saved')
if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        _fail(error)
