import { describe, expect, it } from "vitest";
import { parseNmapOpenPorts } from "./support/nmapRunner";

describe("Nmap output parser", () => {
  it("extracts open TCP and UDP ports from Nmap output", () => {
    const output = `
PORT    STATE SERVICE
21/tcp  open  ftp
22/tcp  closed ssh
53/udp  open  domain
80/tcp  open  http
445/tcp open  microsoft-ds
`;
    expect(parseNmapOpenPorts(output)).toEqual([
      { port: 21, protocol: "tcp", service: "ftp" },
      { port: 53, protocol: "udp", service: "domain" },
      { port: 80, protocol: "tcp", service: "http" },
      { port: 445, protocol: "tcp", service: "microsoft-ds" },
    ]);
  });

  it("returns an empty array when no ports are open", () => {
    expect(parseNmapOpenPorts("PORT STATE SERVICE\n80/tcp closed http\n")).toEqual([]);
  });
});
