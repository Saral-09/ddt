import { spawn, type ChildProcess } from "node:child_process";
import { buildNmapArgs, type NmapOptions } from "../../../utils/nmapCommand";

export interface NmapRunResult {
  binary: string;
  args: string[];
  stdout: string;
  stderr: string;
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  durationMs: number;
}

export interface RunNmapOptions extends NmapOptions {
  binary?: string;
  timeoutMs?: number;
}

/** Parse open TCP/UDP rows from normal Nmap output. */
export function parseNmapOpenPorts(output: string): Array<{
  port: number;
  protocol: "tcp" | "udp";
  service?: string;
}> {
  const results: Array<{ port: number; protocol: "tcp" | "udp"; service?: string }> = [];
  const row = /^\s*(\d+)\/(tcp|udp)\s+open(?:\s+(\S+))?/gm;
  for (const match of output.matchAll(row)) {
    results.push({
      port: Number(match[1]),
      protocol: match[2] as "tcp" | "udp",
      ...(match[3] ? { service: match[3] } : {}),
    });
  }
  return results;
}

/**
 * Execute Nmap safely as an argv array (shell:false). This runner is for the
 * optional local integration test, not imported by the React application.
 */
export async function runNmap(options: RunNmapOptions): Promise<NmapRunResult> {
  const binary = options.binary ?? "nmap";
  const timeoutMs = options.timeoutMs ?? 90_000;
  const args = buildNmapArgs(options);
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    let child: ChildProcess;
    try {
      child = spawn(binary, args, {
        shell: false,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      reject(error);
      return;
    }

    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      // Prevent a hung child from keeping the Vitest process alive forever.
      setTimeout(() => child.kill("SIGKILL"), 2_000).unref();
    }, timeoutMs);

    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string) => { stdout += chunk; });
    child.stderr?.on("data", (chunk: string) => { stderr += chunk; });

    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });

    child.once("close", (code, signal) => {
      clearTimeout(timer);
      if (timedOut) {
        reject(new Error(`Nmap exceeded the ${timeoutMs}ms timeout for ${options.target}`));
        return;
      }
      resolve({
        binary,
        args,
        stdout,
        stderr,
        exitCode: code,
        signal: signal as NodeJS.Signals | null,
        durationMs: Date.now() - startedAt,
      });
    });
  });
}
