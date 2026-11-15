# Unicornscan — QA fixture card

**Category:** Port scanner

**Fixture mode:** `single_lab_port_only`

## Simple test

Use one explicitly selected lab IP and one TCP port with conservative settings if the component supports it.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

No broad/high-rate scan.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
