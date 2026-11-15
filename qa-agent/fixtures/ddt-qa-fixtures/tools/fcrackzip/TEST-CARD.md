# Fcrackzip — QA fixture card

**Category:** ZIP password recovery

**Fixture mode:** `offline_file_only`

## Simple test

Use `common/archive/ddt-password-protected.zip`; fixture password is documented in `PASSWORD.txt`.

## Fixture files

- `common/archive/ddt-password-protected.zip`

## Safety / limitations

Only the supplied synthetic archive; do not target user archives.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
