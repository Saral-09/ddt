# dmitry — QA fixture card

**Category:** Information gathering

**Fixture mode:** `local_or_help_only`

## Simple test

Use `127.0.0.1` for basic target validation; local DNS/WHOIS data may be unavailable.

## Fixture files

- No dedicated binary fixture. Use the shared fixtures only where the selected component accepts them.

## Safety / limitations

Do not query third-party targets.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
