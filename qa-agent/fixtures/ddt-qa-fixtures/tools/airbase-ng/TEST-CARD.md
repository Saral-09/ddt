# Airbase NG — QA fixture card

**Category:** Wireless AP creation

**Fixture mode:** `hardware_required`

## Simple test

No runnable fixture. Verify form rendering and dependency/help only; requires a dedicated isolated wireless adapter/AP lab.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

Do not create rogue APs or transmit beacons as an automated fixture.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
