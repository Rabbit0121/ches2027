Timing-guided S-box search and construction

This directory contains the core algorithms shared by the 15, 45, and 55 nm
versions. Tool installation, foundry libraries, experiment histories, and batch
scheduling are omitted. Python 3.10+ is sufficient for the reference check;
native fixed-delay search also needs PowerShell 7 with a .NET 6+ runtime.

Default case
  APN6, 45 nm fixed gate costs, 21 gate types, counted input BUF/INV cells,
  10-hour search budget, no additional depth limit.
  The supplied six-output reference circuit evaluates to 157298 fs = 157.298 ps.
  This is a fixed gate-delay value, not a synthesized STA value.

  Check the supplied circuit:
    python the/path/of/ches2027/main.py verify

  Search from the truth table:
    python the/path/of/ches2027/main.py search --output the/path/of/results

The search builds its initial circuit from the truth table; it does not load
the reference circuit. The reference check and a new search are separate tasks.
The default parameters describe the APN6 instance; a time-limited search may
finish with a different bound. This compact package does not include the
independent lower-bound proof.

Core mechanism
  Forward gates generate functions. Reverse gate relations request a missing
  child on selected truth-table rows; later matches reconstruct parents and
  feed them back into generation. Fixed costs permit child deadlines; NLDM/STA
  retain physical alternatives and time complete circuits before acceptance.

Code guide
  core:                 Boolean gates, truth tables, and ordered circuit DAGs.
  search / fixed:       Native forward/reverse search, symmetry reduction,
                        deadline domains, indexed matching, and cover queries.
  search / bidirectional:
                        Physical alternatives and persistent missing-input
                        requests; completed parents feed back into generation.
  timing:               NLDM propagation, characterized gate-sequence ranking,
                        and the mapping/sizing/STA adapter interface.
  construction:         Coordinate pool and component-space assembly.
  examples:             Public APN6 lookup table and its reference circuit.

Timing and process selection
  profiles.json separates the three process cost tables and library locations.
  config.json selects the default policy, budgets, and external EDA command.
  Replace every the/path/of/xxx placeholder before using an external backend.
  The 157.298 ps reference applies to the default 45 nm fixed-cost model only.

  NLDM uses actual sink-pin loads and rise/fall tables. STA ranks proposals by
  characterized gate sequences, falling back to isolated synthesis and STA.
  Complete candidates are always evaluated as complete circuits. The STA adapter
  receives JSON on stdin and returns delay_ps, outputs_ps, mapped_graph, and
  sat_equivalent=true on stdout; its implementation is external. It checks SAT
  equivalence for every mapped circuit. The interface supplies the mapping
  and sizing scripts, protects paid input cells, and also checks truth tables
  for circuits with at most ten inputs. Use canonical gate/pin aliases.
  The unit reader supports the ps/fF conversions needed by all three processes;
  physical tables must come from the selected process, without delay scaling.
  NLDM background-load rankings use direct tables in this compact version.

Construction
  Default: STA guidance, one-hour pool generation plus two-hour assembly.
  Targets: 4 bits U4/L8; 5 bits U6/L16; 6 bits U8/L24 (full Walsh amplitude).
  EBP classes are allowed; there are no extra component-degree restrictions.
  A new coordinate is tested against the existing XOR component space for
  balance and linearity. Completed mappings undergo exact differential tests,
  then joint timing trials over alternative coordinate implementations.

    python the/path/of/ches2027/main.py construct --bits 4 --output the/path/of/results4
    python the/path/of/ches2027/main.py construct --bits 5 --output the/path/of/results5
    python the/path/of/ches2027/main.py construct --bits 6 --output the/path/of/results6

  Select another process with --technology 15 or --technology 55; use
  --policy nldm for direct source-graph NLDM evaluation. No new mapping is
  guaranteed within a fixed time budget.
