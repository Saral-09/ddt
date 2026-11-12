import { describe, expect, it } from "vitest";
import { parseNmapOpenPorts, runNmap } from "./support/nmapRunner";

const enabled = process.env.RUN_NMAP_INTEGRATION === "1";
const target = process.env.NMAP_TEST_TARGET;
const ports = process.env.NMAP_TEST_PORTS ?? "21,80,135,139,445";
const expectedOpenPorts = (process.env.NMAP_EXPECT_OPEN_PORTS ?? "21,80,135,139,445")
  .split(",")
  .map((value) => Number(value.trim()))
  .filter((value) => Number.isInteger(value) && value > 0 && value <= 65535);

describe.skipIf(!enabled || !target)("Nmap real-binary integration (opt-in)", () => {
  it("scans the configured lab host and finds expected open TCP ports", async () => {
    expect(expectedOpenPorts.length, "Set NMAP_EXPECT_OPEN_PORTS to at least one known open port").toBeGreaterThan(0);
    const result = await runNmap({
      target: target!,
      ports,
      scanType: "TCP Connect Scan",
      timing: "Aggressive",
      timeoutMs: 90_000,
    });

    const output = `${result.stdout}\n${result.stderr}`;
    expect(result.exitCode, output).toBe(0);

    const openTcpPorts = new Set(
      parseNmapOpenPorts(output)
        .filter((entry) => entry.protocol === "tcp")
        .map((entry) => entry.port),
    );

    for (const expectedPort of expectedOpenPorts) {
      expect(openTcpPorts.has(expectedPort), `Expected ${expectedPort}/tcp open.\n${output}`).toBe(true);
    }
  }, 100_000);

  it("performs version detection on the configured HTTP port", async () => {
    const httpPort = Number(process.env.NMAP_HTTP_PORT ?? "80");
    const result = await runNmap({
      target: target!,
      ports: String(httpPort),
      scanType: "TCP Connect Scan",
      timing: "Aggressive",
      versionDetection: true,
      timeoutMs: 90_000,
    });

    const output = `${result.stdout}\n${result.stderr}`;
    expect(result.exitCode, output).toBe(0);
    expect(parseNmapOpenPorts(output).some((entry) => entry.port === httpPort && entry.protocol === "tcp"), output).toBe(true);
  }, 100_000);
});
