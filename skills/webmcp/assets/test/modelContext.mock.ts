// Fake document.modelContext for vitest/jsdom. Records tools; abort removes them.
export interface RegisteredTool {
  name: string;
  description?: string;
  inputSchema?: unknown;
  annotations?: Record<string, boolean>;
  execute: (input: any, ctx: { signal: AbortSignal }) => Promise<unknown>;
}

export interface ModelContextMock {
  tools: Map<string, RegisteredTool>;
  registerTool(tool: RegisteredTool, options?: { signal?: AbortSignal }): void;
  call(name: string, input?: unknown): Promise<unknown>;
}

export function installModelContextMock(): ModelContextMock {
  const tools = new Map<string, RegisteredTool>();
  const mock: ModelContextMock = {
    tools,
    registerTool(tool, options) {
      if (tools.has(tool.name)) throw new Error(`duplicate tool: ${tool.name}`);
      tools.set(tool.name, tool);
      options?.signal?.addEventListener("abort", () => tools.delete(tool.name));
    },
    call(name, input = {}) {
      const tool = tools.get(name);
      if (!tool) throw new Error(`no such tool: ${name}`);
      return tool.execute(input, { signal: new AbortController().signal });
    },
  };
  Object.defineProperty(document, "modelContext", { value: mock, configurable: true });
  return mock;
}

export function uninstallModelContextMock(): void {
  delete (document as any).modelContext;
}
