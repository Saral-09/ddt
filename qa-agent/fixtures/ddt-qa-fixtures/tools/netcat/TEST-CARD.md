# Netcat — QA fixture card

**Category:** TCP client/server

**Fixture mode:** `loopback_service`

## Simple test

Start `common/local-services/echo_server.py`, then connect to `127.0.0.1:18081` and send `DDT-QA`.

## Fixture files

- `common/local-services/echo_server.py`

## Safety / limitations

Loopback-only echo service.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
