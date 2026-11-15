# Nmap — QA fixture card

**Category:** Network scanner

**Fixture mode:** `single_lab_host`

## Simple test

Use `192.168.1.201` and ports `21,80,135,139,445` when explicitly requested; previously observed open-port results are historical, not guaranteed.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

One host and selected ports only.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
