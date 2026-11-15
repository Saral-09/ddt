# Tiger — QA fixture card

**Category:** Unix security audit

**Fixture mode:** `manual_host_audit`

## Simple test

Use help/configuration inspection first. A full audit examines the machine running the tool.

## Fixture files

- `common/logs/auth.log`

## Safety / limitations

Do not launch automatically; review audit scope first.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
