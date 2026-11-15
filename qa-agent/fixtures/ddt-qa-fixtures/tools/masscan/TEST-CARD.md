# Masscan — QA fixture card

**Category:** High-speed port scanner

**Fixture mode:** `single_lab_port_only`

## Simple test

If explicitly approved, scan one port on one lab IP at a very low rate.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

Never use broad ranges or high rates.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
