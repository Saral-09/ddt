# Arpaname — QA fixture card

**Category:** Reverse DNS lookup

**Fixture mode:** `lab_or_loopback`

## Simple test

Use `127.0.0.1` for loopback validation or an explicitly selected lab IP from `lab-targets.json`.

## Fixture files

- - `common/targets/lab-targets.json`

## Safety / limitations

DNS result depends on local resolver.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
