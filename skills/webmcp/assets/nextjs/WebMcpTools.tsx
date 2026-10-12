"use client";

import { useEffect } from "react";

export type JsonSchema = Record<string, unknown>;

export interface WebMcpTool<I = any> {
  name: string;
  description: string;
  inputSchema: JsonSchema;
  annotations?: {
    readOnlyHint?: boolean;
    consequentialHint?: boolean;
    untrustedContentHint?: boolean;
    debugging?: boolean;
  };
  execute: (input: I, ctx: { signal: AbortSignal }) => Promise<unknown>;
}

interface ModelContextLike {
  registerTool(tool: WebMcpTool, options?: { signal?: AbortSignal }): void | Promise<unknown>;
}

/** Registers the given tools on document.modelContext; no-op when unsupported. */
export function WebMcpTools({ tools }: { tools: WebMcpTool[] }) {
  useEffect(() => {
    const mc = (document as unknown as { modelContext?: ModelContextLike }).modelContext;
    if (!mc || typeof mc.registerTool !== "function") return;
    const ac = new AbortController();
    for (const tool of tools) {
      try {
        // Chrome 156: the returned promise rejects with AbortError on unregister.
        Promise.resolve(mc.registerTool(tool, { signal: ac.signal })).catch((err) => {
          if (!ac.signal.aborted) console.warn(`WebMCP: ${tool.name} was rejected`, err);
        });
      } catch (err) {
        console.warn(`WebMCP: failed to register ${tool.name}`, err);
      }
    }
    return () => ac.abort();
  }, [tools]);

  return null;
}
