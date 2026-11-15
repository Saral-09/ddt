# Foremost — QA fixture card

**Category:** File carving

**Fixture mode:** `offline_file`

## Simple test

Select `common/forensics/ddt-sample-disk.img`; expected embedded types include JPEG and ZIP.

## Fixture files

- `common/forensics/ddt-sample-disk.img`

## Safety / limitations

Output to a new disposable directory.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
