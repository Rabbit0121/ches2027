# Timing-guided S-box search and construction

Core algorithms for 15, 45, and 55 nm gate libraries. Python 3.10+ is required;
native Fixed search and the full proof computation also use PowerShell 7 with
a .NET 6+ runtime.

## Default case

APN6, 45 nm fixed gate costs, 21 gate types, counted input BUF/INV cells,
a 10-hour search budget, and unrestricted circuit depth. The supplied six-output
circuit has a fixed-model delay of **157.298 ps**.

Verify the supplied circuit:

```sh
python -B the/path/of/ches2027/main.py verify
```

Search from the truth table, using a DNF/ANF initial circuit:

```sh
python -B the/path/of/ches2027/main.py search --output the/path/of/results
```

## Core mechanism and layout

Forward gates generate functions. Reverse gate relations request a missing child
on selected truth-table rows. Later matches reconstruct parents and return them
to generation. Fixed costs provide child deadlines; NLDM and practice retain
physical alternatives and time complete circuits before acceptance.

| Component | Purpose |
| --- | --- |
| `core` | Boolean gates, truth tables, and ordered circuit DAGs |
| `search` → `fixed` | Fixed-cost search, symmetry reduction, indexed matching, and cover queries |
| `search` → `fixed` → `proof` | Structure-first APN6 lower-bound computation and audit |
| `search` → `nldm` | NLDM search and source-DAG table propagation |
| `search` → `practice` | Path characterization, mapped-STA search, and EDA adapter |
| `search` → `common` | Shared archive, reverse requests, and reconstructed-parent feedback |
| `timing` | Liberty reading, unit conversion, and gate aliases |
| `construction` | Coordinate pool and component-space assembly |
| `examples` | APN6 lookup table and reference circuit |

## Timing and process selection

`profiles.json` contains the three process cost tables and library locations.
`config.json` selects the timing policy, budgets, and EDA command. Replace
`the/path/of/xxx` with the desired locations.

```sh
python -B the/path/of/ches2027/main.py search --policy nldm --output the/path/of/nldm_results
python -B the/path/of/ches2027/main.py search --policy practice --output the/path/of/practice_results
```

Select a process with `--technology 15`, `--technology 45`, or `--technology 55`.
`sta` is an alias for `practice`.

NLDM propagates rise/fall timing tables under actual sink-pin loads and evaluates
background-load rankings directly. Practice ranks proposals using characterized
gate sequences, with isolated synthesis and STA as a fallback, and measures
complete candidates after mapping and sizing.

Practice uses an external EDA adapter: JSON stdin carries the graph, library,
mapping/sizing scripts, and timing conditions. JSON stdout returns `delay_ps`,
`outputs_ps`, `mapped_graph`, and `sat_equivalent=true`. The interface preserves
paid input cells and checks truth tables for circuits with at most ten inputs.
Libraries and graphs use canonical gate/pin aliases; table units are ps/fF.

## APN6 proof

The proof module enumerates structures before input assignments and checks all
26 root cases at 157297 fs. NAND2 uses weighted exceptions; OAI21 uses
common-center matching. Select `--proof-stage plan` to generate the structural
plan, `check` for local checks, `run` for the full computation, or `audit` to
recheck a completed run.

```sh
python -B the/path/of/ches2027/main.py proof --proof-stage plan --output the/path/of/proof_plan
```

## Construction

Default: practice guidance, one-hour pool generation, and two-hour assembly.
Targets are 4-bit U4/L8, 5-bit U6/L16, and 6-bit U8/L24, using full Walsh
amplitude. EBP classes and all component degrees are allowed.

Each new coordinate is tested against the existing XOR component space for
balance and linearity. Completed mappings undergo exact differential tests,
followed by joint timing trials over alternative coordinate implementations.

```sh
python -B the/path/of/ches2027/main.py construct --bits 4 --output the/path/of/results4
python -B the/path/of/ches2027/main.py construct --bits 5 --output the/path/of/results5
python -B the/path/of/ches2027/main.py construct --bits 6 --output the/path/of/results6
```

Use `--policy nldm` for source-graph NLDM evaluation.
