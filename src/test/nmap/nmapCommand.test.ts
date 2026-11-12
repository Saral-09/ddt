import { describe, expect, it } from "vitest";
import { buildNmapArgs, executeNmap, validateNmapPorts } from "../../utils/nmapCommand";

describe("DDT Nmap command builder", () => {
  it("builds a basic TCP connect scan", () => {
    expect(buildNmapArgs({ target: "192.168.1.201" })).toEqual([
      "-sT", "-T3", "192.168.1.201",
    ]);
  });

  it("dispatches the generated argv through the injected DDT command executor", async () => {
    const executor = async (command: string, args: string[]) => ({ command, args });
    const result = await executeNmap(
      { target: "192.168.1.201", ports: "80,443", versionDetection: true },
      executor,
    );

    expect(result).toEqual({
      command: "nmap",
      args: ["-sT", "-T3", "-p", "80,443", "-sV", "192.168.1.201"],
    });
  });

  it("builds a targeted scan with a port list and range", () => {
    expect(buildNmapArgs({
      target: "192.168.1.201",
      ports: "21,80,135,139,445,8000-8010",
      scanType: "TCP Connect Scan",
      timing: "Aggressive",
    })).toEqual([
      "-sT", "-T4", "-p", "21,80,135,139,445,8000-8010", "192.168.1.201",
    ]);
  });

  it.each([
    ["TCP Connect Scan", "-sT"],
    ["UDP Scan", "-sU"],
    ["ACK Scan", "-sA"],
  ] as const)("maps the %s scan type to %s", (scanType, flag) => {
    expect(buildNmapArgs({ target: "127.0.0.1", scanType })).toContain(flag);
  });

  it("adds version, OS, verbose, IPv6 and no-ping options", () => {
    expect(buildNmapArgs({
      target: "2001:db8::10",
      versionDetection: true,
      osDetection: true,
      verbose: true,
      ipv6: true,
      skipHostDiscovery: true,
    })).toEqual([
      "-sT", "-T3", "-sV", "-O", "-v", "-6", "-Pn", "2001:db8::10",
    ]);
  });

  it("adds aggressive mode without duplicating version and OS flags", () => {
    expect(buildNmapArgs({
      target: "127.0.0.1",
      aggressive: true,
      versionDetection: true,
      osDetection: true,
    })).toEqual(["-sT", "-T3", "-A", "127.0.0.1"]);
  });

  it("adds an NSE script selector as a separate argument", () => {
    expect(buildNmapArgs({ target: "192.168.1.201", scriptScan: "http-title,safe" })).toEqual([
      "-sT", "-T3", "--script", "http-title,safe", "192.168.1.201",
    ]);
  });

  it("rejects missing or option-like targets", () => {
    expect(() => buildNmapArgs({ target: "" })).toThrow(/target/i);
    expect(() => buildNmapArgs({ target: "-iL" })).toThrow(/target/i);
    expect(() => buildNmapArgs({ target: "192.168.1.1\n--script=evil" })).toThrow(/target/i);
  });

  it.each(["0", "65536", "80,", ",80", "80,,443", "443-80", "abc", "80-65536"])(
    "rejects invalid port expression %s",
    (ports) => expect(() => validateNmapPorts(ports)).toThrow(),
  );

  it("accepts valid single ports, lists and ranges", () => {
    expect(validateNmapPorts("80")).toBe("80");
    expect(validateNmapPorts("22,80,443")).toBe("22,80,443");
    expect(validateNmapPorts("8000-8010")).toBe("8000-8010");
  });

  it("rejects unsupported timing values and invalid NSE selectors", () => {
    expect(() => buildNmapArgs({ target: "127.0.0.1", timing: 6 as never })).toThrow(/timing/i);
    expect(() => buildNmapArgs({ target: "127.0.0.1", scriptScan: "http-title; touch /tmp/pwned" })).toThrow(/script/i);
  });
});
