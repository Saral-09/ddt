# Testssl — QA fixture card

**Category:** TLS configuration test

**Fixture mode:** `local_tls_only`

## Simple test

Start `common/tls/server.py` and test `127.0.0.1:18443`. The certificate is self-signed.

## Fixture files

- `common/tls/localhost-cert.pem`
- `common/tls/localhost-key.pem`

## Safety / limitations

Loopback-only; certificate key is test-only.

## Instructions for the DDT QA agent

Inspect this tool's actual React component and its user guide before filling fields. Do not assume field names, selectors, CLI arguments, or that this fixture is valid for the tool. Populate the actual UI only with inputs supported by the component. If the component needs a missing service, capture, API key, adapter, or real `.rt` table, mark the test `test_gap` or `dependency_missing`; do not fabricate a valid input.
