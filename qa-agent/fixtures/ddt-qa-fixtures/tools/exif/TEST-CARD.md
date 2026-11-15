# Exif — QA fixture card

**Category:** Image metadata extraction

**Fixture mode:** `offline_file`

## Simple test

Select `common/images/ddt-exif-sample.jpg`.

## Fixture files

- `common/images/ddt-exif-sample.jpg`

## Safety / limitations

Synthetic EXIF metadata only.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
