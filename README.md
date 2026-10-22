# Process Workbench

A small, dependency-free Python command-line tool for checking directed process workflows and summarizing a reproducible example run.

## Requirements

- Python 3.11 or newer
- No third-party runtime packages

## Run from a checkout

From the project root:

```console
python src/main.py examples/order-approval.json
```

The command prints the reachable and unreachable steps, any invalid transitions, detected cycles, and the duration of the example path. The example process includes an alternate route and a loop; the chosen sample path reaches a terminal step.

## Optional report

Choose the report format with the file extension. Reports are created as new files; existing files and the source definition are never overwritten.

```console
python src/main.py examples/order-approval.json --report report.json
python src/main.py examples/order-approval.json --report report.csv
python src/main.py examples/order-approval.json --report report.txt
```

The CSV uses semicolons as separators. Parent folders are created when needed.

## Process definition

Each file is a UTF-8 JSON object with:

- `name`: a short process name
- `start_step`: the ID where the process begins
- `steps`: objects containing a unique `id`, display `name`, non-negative `duration_minutes`, and a list of `next_steps` IDs. An empty list marks a terminal step.
- `sample_path`: a valid sequence of connected step IDs beginning at `start_step` and ending at a terminal step

The analyzer reports all nodes reachable from the start, unreachable nodes, graph cycles, unknown transition targets, and problems in the sample path. It does not pick a branch automatically: the `sample_path` makes the example run explicit and repeatable.

## Exit codes

- `0`: the definition and sample path are valid
- `1`: the input cannot be read/parsed or the process contains validation errors
- `2`: command-line usage or report output error

## Scope

This is a local teaching/demo tool for small JSON process graphs. It does not execute external actions, connect to workflow services, or modify the process definition.
