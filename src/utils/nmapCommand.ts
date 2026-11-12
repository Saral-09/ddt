/**
 * Pure Nmap command builder shared by the DDT Nmap component and Vitest.
 * Keep this file free of Node.js and Tauri imports so it can be used by React.
 */

export type NmapScanType =
  | "TCP Connect Scan"
  | "UDP Scan"
  | "ACK Scan"
  | "tcp-connect"
  | "udp"
  | "ack";

export type NmapTiming = 0 | 1 | 2 | 3 | 4 | 5 | "T0" | "T1" | "T2" | "T3" | "T4" | "T5"
  | "Paranoid" | "Sneaky" | "Polite" | "Normal" | "Aggressive" | "Insane";

export interface NmapOptions {
  target: string;
  ports?: string;
  scanType?: NmapScanType;
  timing?: NmapTiming;
  versionDetection?: boolean;
  osDetection?: boolean;
  aggressive?: boolean;
  verbose?: boolean;
  scriptScan?: string;
  ipv6?: boolean;
  skipHostDiscovery?: boolean;
}

const SCAN_FLAGS: Record<NmapScanType, string> = {
  "TCP Connect Scan": "-sT",
  "UDP Scan": "-sU",
  "ACK Scan": "-sA",
  "tcp-connect": "-sT",
  udp: "-sU",
  ack: "-sA",
};

const TIMING_VALUES: Record<string, string> = {
  Paranoid: "0",
  Sneaky: "1",
  Polite: "2",
  Normal: "3",
  Aggressive: "4",
  Insane: "5",
};

function normaliseTiming(timing: NmapTiming | undefined): string {
  if (timing === undefined) return "3";
  if (typeof timing === "number") {
    if (!Number.isInteger(timing) || timing < 0 || timing > 5) {
      throw new Error("Nmap timing must be an integer from 0 to 5");
    }
    return String(timing);
  }

  if (timing in TIMING_VALUES) return TIMING_VALUES[timing];
  const match = /^T([0-5])$/.exec(timing);
  if (match) return match[1];
  throw new Error(`Unsupported Nmap timing value: ${timing}`);
}

/** Validate numeric port lists/ranges accepted by DDT's Nmap port field. */
export function validateNmapPorts(ports: string): string {
  const value = ports.trim();
  if (!value) throw new Error("At least one port or port range is required");

  const parts = value.split(",").map((part) => part.trim());
  if (parts.some((part) => !part)) throw new Error("Port list contains an empty entry");

  for (const part of parts) {
    const range = /^(\d+)(?:-(\d+))?$/.exec(part);
    if (!range) throw new Error(`Invalid port entry: ${part}`);

    const start = Number(range[1]);
    const end = range[2] === undefined ? start : Number(range[2]);

    if (
      !Number.isInteger(start) ||
      !Number.isInteger(end) ||
      start < 1 ||
      end > 65535 ||
      start > end
    ) {
      throw new Error("Port numbers must be in range 1-65535 and ranges must be ascending");
    }
  }

  return parts.join(",");
}

function validateTarget(target: string): string {
  const value = target.trim();
  // Nmap accepts hostnames, IPv4/IPv6 addresses, CIDRs and target ranges.
  // This deliberately rejects whitespace/control characters and option-like values.
  if (!value || value.startsWith("-") || /[\s\u0000-\u001f]/.test(value)) {
    throw new Error("Enter a valid Nmap target (IP address or hostname)");
  }
  return value;
}

function validateScript(script: string): string {
  const value = script.trim();
  // Nmap script names/selectors can contain letters, digits, dots, commas,
  // underscores, plus, slash, wildcard and hyphen. No shell is involved,
  // but keep the value constrained to the expected NSE selector syntax.
  if (!value || !/^[A-Za-z0-9_.*,+/-]+$/.test(value)) {
    throw new Error("Invalid Nmap NSE script name or selector");
  }
  return value;
}

/**
 * Build argv for `nmap` without shell concatenation. The target is always last.
 * This is the function the DDT Nmap component should call before executing Nmap.
 */
export function buildNmapArgs(options: NmapOptions): string[] {
  const target = validateTarget(options.target);
  const scanType = options.scanType ?? "TCP Connect Scan";
  const scanFlag = SCAN_FLAGS[scanType];
  if (!scanFlag) throw new Error(`Unsupported Nmap scan type: ${String(scanType)}`);

  const args: string[] = [scanFlag, `-T${normaliseTiming(options.timing)}`];

  if (options.ports !== undefined && options.ports.trim() !== "") {
    args.push("-p", validateNmapPorts(options.ports));
  }

  if (options.aggressive) {
    args.push("-A");
  } else {
    if (options.versionDetection) args.push("-sV");
    if (options.osDetection) args.push("-O");
  }

  if (options.scriptScan) args.push("--script", validateScript(options.scriptScan));
  if (options.verbose) args.push("-v");
  if (options.ipv6) args.push("-6");
  if (options.skipHostDiscovery) args.push("-Pn");

  args.push(target);
  return args;
}


/**
 * Dispatch the generated argv through an injected executor. DDT's Nmap component
 * can inject its existing CommandHelper method here; Vitest can inject a spy.
 */
export type NmapCommandExecutor<TResult> = (command: string, args: string[]) => Promise<TResult>;

export async function executeNmap<TResult>(
  options: NmapOptions,
  executor: NmapCommandExecutor<TResult>,
): Promise<TResult> {
  const args = buildNmapArgs(options);
  return executor("nmap", args);
}
