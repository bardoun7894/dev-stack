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

  it("handles the AbortError promise on unmount without unhandled rejection", async () => {
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { unmount } = render(<WebMcpTools tools={tools} />);
    unmount();
    await new Promise((r) => setTimeout(r, 0));
    process.off("unhandledRejection", unhandled);
    expect(unhandled).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it("reports a non-abort rejection via console.warn", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    mc.registerTool = () => Promise.reject(new Error("invalid schema"));
    render(<WebMcpTools tools={tools} />);
    await new Promise((r) => setTimeout(r, 0));
    expect(warn).toHaveBeenCalledWith(
      "WebMCP: search_products was rejected",
      expect.any(Error),
    );
    warn.mockRestore();
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
