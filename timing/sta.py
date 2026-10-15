"""Adapter boundary for Yosys/ABC mapping, sizing, equivalence, and OpenSTA."""
import json
import math
import subprocess
from collections import Counter
from ..core.structure import physical_pins
from ..core.model import ARITY
from ..search.fixed.audit import scalar

MAPPING_SCRIPT = ('strash; ifraig; scorr; dc2; dretime; retime; strash; '
                  '&get -n; &dch -f; &nf; &put; buffer; upsize; dnsize; stime -p')
SIZING_SCRIPT = 'upsize -D 1; dnsize -D 1'


def circuit_data(spec):
    """Keep validated canonical connections and loads, without tool metadata."""
    n = spec['n_inputs']
    if type(n) is not int or n < 1:
        raise ValueError('Invalid input count')
    allowed = {kind + '_X' + str(size) for kind in ARITY for size in (1, 2, 4)}
    rows = []
    for j, row in enumerate(spec['gates']):
        cell = row['cell']
        if cell not in allowed:
            raise ValueError('Unsupported mapped gate alias')
        pins = dict(row['pins'])
        if set(pins) != set(physical_pins(cell.rsplit('_X', 1)[0])):
            raise ValueError('Unexpected cell pins')
        if any(type(i) is not int or not 0 <= i < n + j for i in pins.values()):
            raise ValueError('Invalid mapped connections')
        rows.append(dict(cell=cell, pins=pins))
    outputs = []
    for output in spec['outputs']:
        node, load = output['node'], output['load_ff']
        if type(node) is not int or not 0 <= node < n + len(rows):
            raise ValueError('Invalid output connection')
        if not isinstance(load, (int, float)) or not math.isfinite(load) or load < 0:
            raise ValueError('Invalid output load')
        outputs.append(dict(node=node, load_ff=load))
    if not outputs:
        raise ValueError('Missing outputs')
    return dict(n_inputs=n, gates=rows, outputs=outputs)


def output_signatures(graph):
    """Check an aliased, topologically ordered mapped netlist on every input."""
    n = graph['n_inputs']
    signatures = [0] * len(graph['outputs'])
    for x in range(1 << n):
        values = [(x >> i) & 1 for i in range(n)]
        for row in graph['gates']:
            kind = row['cell'].rsplit('_X', 1)[0]
            pins = physical_pins(kind)
            if set(row['pins']) != set(pins):
                raise ValueError('Unexpected cell pins')
            indices = [row['pins'][p] for p in pins]
            if any(type(i) is not int or not 0 <= i < len(values) for i in indices):
                raise ValueError('Invalid mapped connections')
            values.append(scalar(kind, [values[i] for i in indices]))
        for j, output in enumerate(graph['outputs']):
            signatures[j] |= values[output['node']] << x
    return signatures


def input_cells(graph):
    cells = Counter()
    n = graph['n_inputs']
    for row in graph['gates']:
        kind = row['cell'].rsplit('_X', 1)[0]
        for source in row['pins'].values():
            if source < n:
                if kind not in ('BUF', 'INV'):
                    raise ValueError('Unpaid primary-input edge')
                cells[kind, source] += 1
    if any(output['node'] < n for output in graph['outputs']):
        raise ValueError('Unpaid output')
    return cells


class MappedSTA:
    """JSON stdin/stdout adapter; no machine-specific tool installation is bundled.

    The adapter returns delay_ps, outputs_ps, mapped_graph, and sat_equivalent.
    It must preserve paid input cells, map with X1, size with available X1/X2/X4,
    verify SAT equivalence, and time the final graph under the supplied conditions.
    """
    def __init__(self, command, library_path, slew_ps=20., timeout=120.):
        self.command, self.library_path = command, str(library_path)
        self.slew_ps, self.timeout = slew_ps, timeout

    def __call__(self, spec):
        request = dict(graph=spec, liberty=self.library_path, driver='INV_X1',
                       slew_ps=self.slew_ps, wire_capacitance=0., wire_delay=0.,
                       protect_input_cells=True, abc_S=self.slew_ps, abc_G=200,
                       mapping_script=MAPPING_SCRIPT, sizing_script=SIZING_SCRIPT)
        process = subprocess.run(self.command, input=json.dumps(request),
                                 text=True, capture_output=True, timeout=self.timeout)
        if process.returncode:
            raise RuntimeError('The EDA adapter failed')
        result = json.loads(process.stdout)
        # Retain circuit data only; tool replies may also contain local log paths.
        mapped = circuit_data(result['mapped_graph'])
        if mapped['n_inputs'] != spec['n_inputs'] or result.get('sat_equivalent') is not True:
            raise ValueError('Mapped circuit lacks verified SAT equivalence')
        # Characterization trees can have many more inputs than an S-box.
        # Their equivalence uses the adapter's SAT check, not exponential enumeration.
        if spec['n_inputs'] <= 10 and output_signatures(mapped) != output_signatures(spec):
            raise ValueError('Source/mapped truth-table mismatch')
        if input_cells(mapped) != input_cells(spec):
            raise ValueError('Paid input cells changed during mapping')
        if [o['load_ff'] for o in mapped['outputs']] != [o['load_ff'] for o in spec['outputs']]:
            raise ValueError('Mapped output loads changed')
        delays = result['outputs_ps']
        if len(delays) != len(spec['outputs']) or any(not math.isfinite(v) or v < 0 for v in delays):
            raise ValueError('Invalid output timing')
        if not math.isclose(result['delay_ps'], max(delays), abs_tol=1e-8):
            raise ValueError('Inconsistent maximum delay')
        depth = [0] * mapped['n_inputs']
        for row in mapped['gates']:
            depth.append(1 + max(depth[i] for i in row['pins'].values()))
        return dict(delay_ps=float(result['delay_ps']), outputs_ps=list(delays),
                    mapped_graph=mapped, sat_equivalent=True,
                    gate_count=len(mapped['gates']),
                    max_depth=max(depth[o['node']] for o in mapped['outputs']))
