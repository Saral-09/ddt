# Gitleaks — QA fixture card

**Category:** Secret scanning

**Fixture mode:** `offline_file`

## Simple test

Scan `common/repo/` containing obviously fake test markers.

## Fixture files

- `common/repo/`

## Safety / limitations

All secret-like strings are invalid test placeholders.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
