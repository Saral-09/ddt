# GoldenEye — QA fixture card

**Category:** HTTP denial-of-service

**Fixture mode:** `manual_only`

## Simple test

UI validation and help-only checks.

## Fixture files

- `common/targets/localhost-url.txt`

## Safety / limitations

No load or denial-of-service execution.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
