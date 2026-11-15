# DNSRecon — QA fixture card

**Category:** DNS reconnaissance

**Fixture mode:** `manual_local_dns`

## Simple test

Use `ddt.test` with a lab resolver only if configured.

## Fixture files

- `common/dns/example-zone.txt`

## Safety / limitations

No zone transfer attempts against third parties.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
