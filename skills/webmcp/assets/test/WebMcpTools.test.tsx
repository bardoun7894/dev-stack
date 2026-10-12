import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { WebMcpTools, type WebMcpTool } from "../nextjs/WebMcpTools";
import {
  installModelContextMock,
  uninstallModelContextMock,
  type ModelContextMock,
} from "./modelContext.mock";

const execute = vi.fn(async () => ({ ok: true }));
const tools: WebMcpTool[] = [
  {
    name: "search_products",
    description: "Search the catalog",
    inputSchema: { type: "object", properties: { q: { type: "string" } } },
    annotations: { readOnlyHint: true },
    execute,
  },
];

describe("WebMcpTools", () => {
  let mc: ModelContextMock;
  beforeEach(() => {
    mc = installModelContextMock();
  });
  afterEach(() => uninstallModelContextMock());

  it("registers tools on mount and unregisters on unmount", () => {
    const { unmount } = render(<WebMcpTools tools={tools} />);
    expect(mc.tools.has("search_products")).toBe(true);
    unmount();
    expect(mc.tools.size).toBe(0);
  });

  it("calls execute with the input", async () => {
    render(<WebMcpTools tools={tools} />);
    await mc.call("search_products", { q: "shoes" });
    expect(execute).toHaveBeenCalledWith({ q: "shoes" }, expect.anything());
  });

  it("is a no-op when document.modelContext is unsupported", () => {
    uninstallModelContextMock();
    expect(() => render(<WebMcpTools tools={tools} />)).not.toThrow();
  });
});
