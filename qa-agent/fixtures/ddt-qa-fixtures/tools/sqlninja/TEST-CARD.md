# Sqlninja — QA fixture card

**Category:** SQL Server exploitation

**Fixture mode:** `manual_only`

## Simple test

Form validation and help-only checks. No SQL Server target is bundled.

## Fixture files

- No dedicated binary fixture. Use the shared fixtures only where the selected component accepts them.

## Safety / limitations

No exploitation.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
