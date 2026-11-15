# Sherlock — QA fixture card

**Category:** Username OSINT

**Fixture mode:** `manual_only`

## Simple test

UI validation with `ddt-qa-fixture-user` only; do not perform internet-wide account checks automatically.

## Fixture files

- `common/wordlists/synthetic-usernames.txt`

## Safety / limitations

No public account enumeration.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
