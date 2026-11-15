# Metagoofil — QA fixture card

**Category:** Document metadata collection

**Fixture mode:** `offline_or_local_docs`

## Simple test

Use the included DOCX/PDF files for metadata inspection; remote harvesting is not part of this fixture.

## Fixture files

- `common/documents/ddt-sample-report.docx`
- `common/documents/ddt-sample-report.pdf`

## Safety / limitations

No internet document harvesting.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
