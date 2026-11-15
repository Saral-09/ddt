# DDT QA Fixture Pack (73 tools)

Version: 1.0
Generated: 2026-11-12

This pack provides small, synthetic, local test inputs and a test card for every one of the 73 tools in the supplied DDT route registry. It is designed for the DDT AI QA agent to inspect and fill the real UI. It is **not** a guarantee that every fixture is accepted by every current component version. Always inspect the tool component and guide first.

## Start here

- `fixtures-manifest.json`: machine-readable index for all 73 tool routes.
- `fixtures-manifest.csv`: spreadsheet-friendly index.
- `AGENT-USAGE.md`: instructions for Foundry/QA agent.
- `FILE-FIXTURES.md`: quick index of reusable file inputs.
- `LAB-SCOPE.md`: lab addresses and safety boundaries.
- `tools/<tool-slug>/TEST-CARD.md`: one simple scenario per tool.
- `common/`: reusable local files, sample captures, hashes, docs, web server and disposable test inputs.

## Quick setup

Start the local harmless web fixture (loopback only):

```bash
cd common/local-web
python3 server.py
```

Base URL: `http://127.0.0.1:18080/`

For a local TCP echo test, in another terminal:

```bash
cd common/local-services
python3 echo_server.py
```

Echo endpoint: `127.0.0.1:18081` (one connection).

For a local TLS test, in another terminal:

```bash
cd common/tls
python3 server.py
```

TLS endpoint: `https://127.0.0.1:18443` (self-signed certificate).

## Test data

- Image: `common/images/ddt-exif-sample.jpg`
- Documents: `common/documents/ddt-sample-report.docx`, `.pdf`
- File carving input: `common/forensics/ddt-sample-disk.img`
- Packet capture: `common/pcap/ddt-synthetic-http.pcap`
- Offline MD5/SHA1 hashes: `common/hashes/`
- Tiny wordlist: `common/wordlists/tiny-fixture-words.txt`
- Password-protected ZIP: `common/archive/ddt-password-protected.zip`; fixture password is `ddt-fixture-123`
- Synthetic source repository for Gitleaks: `common/repo/`
- Nuclei health-check template: `common/nuclei/ddt-local-health.yaml`
- Disposable RainbowCrack table generator: `common/rainbowcrack/generate-disposable-table.sh`

The wordlist and password fixtures are deliberately tiny and for offline test hashes/archives only.

## Important limitations

Some DDT tools are active attack, denial-of-service, credential attack, wireless attack, exploit-generation, or privileged tools. For those, the pack provides UI/help/argument-validation scenarios only and explicitly does not include a runnable attack recipe. Review each `TEST-CARD.md` and the `fixture_mode` value before execution.

No fake `.rt` file is included. Rtsort requires a valid RainbowCrack `.rt` table. The included manual generator creates a tiny table only if RainbowCrack is installed; it writes to a disposable output directory and must be run manually.

No real API keys, passwords, personal information, production files, WordPress server, SMB server, SNMP agent, FTP server, wireless access point, or intentionally vulnerable web application is included.

## Recommended QA outcomes

Use these statuses accurately:
- `passed`: actual UI/CLI result matched a reliable fixture expectation.
- `failed`: deterministic mismatch or error against a valid fixture.
- `executed_unverified`: tool ran but no reliable oracle exists.
- `test_gap`: a needed service/fixture/interaction is unavailable.
- `dependency_missing`: required executable or runtime is unavailable.
- `execution_blocked`: test is unsafe or outside the approved scope.

A fixture file existing does not authorise execution. Require the ordinary DDT QA approval gate, and retain the local target allowlist.
