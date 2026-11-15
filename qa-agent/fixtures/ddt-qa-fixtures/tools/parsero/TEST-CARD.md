# Parsero — QA fixture card

**Category:** robots.txt analysis

**Fixture mode:** `local_web_only`

## Simple test

Use `http://127.0.0.1:18080/robots.txt`.

## Fixture files

- `common/local-web/robots.txt`

## Safety / limitations

Local fixture only.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
