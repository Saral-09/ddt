# NSLookup — QA fixture card

**Category:** DNS lookup

**Fixture mode:** `loopback_or_lab_dns`

## Simple test

Query `localhost` or a lab DNS name if configured.

## Fixture files

- `common/dns/dns-records.csv`

## Safety / limitations

No public targets by default.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
