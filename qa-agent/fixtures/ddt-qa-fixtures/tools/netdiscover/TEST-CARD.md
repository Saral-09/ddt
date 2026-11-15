# NetDiscover — QA fixture card

**Category:** Network discovery

**Fixture mode:** `manual_single_host`

## Simple test

Validate interface and target fields; actual ARP discovery requires a same-L2 lab and user-selected host.

## Fixture files

- `common/targets/lab-targets.json`

## Safety / limitations

No automatic network range sweep.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
