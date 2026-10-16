Fixed APN6 lower-bound computation

Target: output bit 2 of the supplied APN6 mapping, with the 45 nm integer gate
costs and counted BUF/INV inputs. Exclude delay <=157297 fs; the supplied upper
expression has delay 157298 fs. This module is separate from heuristic search.
Any finite shared DAG can be unfolded into a tree with the same fixed delay.
Repeated substructures still receive independent leaf assignments.

Flow
  1. count_shapes, structures, structure_catalogue:
     Remove internal BUF and cheaper inverter forms; enumerate pin-symmetry
     classes before assigning variables. Small domains have explicit catalogues;
     large products are represented by an exact finite structural grammar.
  2. input_partitions, beam_truths, build_structured_library, StructureImage:
     Expand paid leaf assignments. Variable-renaming orbits and per-structure
     truth-table caches reduce repetition while preserving witnesses.
     structural_filters supplies necessary degree/support/influence conditions.
  3. family_checks:
     Cover all 19 direct non-unary roots and seven irreducible INV tails.
     NAND2 uses nonnegative integer weights plus exhaustive heavy exceptions.
     OAI21 generates all inner families and requires both children to match
     the same center. Dominance reductions keep explicit replacement witnesses.
  4. verify_y2 and family_checks/certify:
     Check catalogue coverage, all function witnesses, finite-cover certificates,
     exception residuals, dominance maps, and completion of every root case.

Quick structural plan:
  python -B the/path/of/ches2027/main.py proof --proof-stage plan --output the/path/of/proof_plan

Small independent checks and upper-expression verification:
  python -B the/path/of/ches2027/main.py proof --proof-stage check --output the/path/of/proof_checks

Complete computation (PowerShell 7 and a .NET 6+ runtime required):
  python -B the/path/of/ches2027/main.py proof --proof-stage run --output the/path/of/proof_results
  Add --resume to continue that same run. Use --proof-stage audit to recheck it.

Only completed exhaustive stages and the final audit establish a lower bound.
Plan/check results and interrupted computations keep global_lower_bound_proved
false. Structure counts are not counts of distinct Boolean functions.
The package contains algorithm source and a public upper expression, without
historical results, large binary intermediates, machine paths, or source snapshots.
