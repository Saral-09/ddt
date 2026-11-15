# Rtsort — QA fixture card

**Category:** Rainbow table sorting

**Fixture mode:** `disposable_local_file`

## Simple test

Generate a tiny disposable `.rt` table first, then select only its output directory.

## Fixture files

- `common/rainbowcrack/generate-disposable-table.sh`

## Safety / limitations

Sorting modifies files; never select a user’s real rainbow-table directory.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
