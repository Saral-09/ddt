# Shodan API tool — QA fixture card

**Category:** Shodan search

**Fixture mode:** `api_key_required`

## Simple test

Use placeholder query text only. Requires the user’s own API key before a real request.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

No API key included; never store credentials in fixture files.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
