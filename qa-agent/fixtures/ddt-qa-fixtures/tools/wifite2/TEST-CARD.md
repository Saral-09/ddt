# Wifite2 — QA fixture card

**Category:** Wireless auditing

**Fixture mode:** `hardware_required`

## Simple test

Help and UI validation only. Requires a dedicated authorised wireless lab and adapter.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

No wireless attacks or handshake capture.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
