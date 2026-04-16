import { describe, it, expect } from "vitest";
import {
  splitFrontmatter,
  loadSkill,
  loadAgent,
} from "../src/skill-loader.js";

describe("splitFrontmatter", () => {
  it("parses a simple frontmatter block", () => {
    const raw = "---\nname: foo\ndescription: a test\n---\nbody here\n";
    const { frontmatter, body } = splitFrontmatter(raw);
    expect(frontmatter.name).toBe("foo");
    expect(frontmatter.description).toBe("a test");
    expect(body).toBe("body here\n");
  });

  it("returns empty frontmatter when no header present", () => {
    const raw = "just a body, no header";
    const { frontmatter, body } = splitFrontmatter(raw);
    expect(frontmatter).toEqual({});
    expect(body).toBe(raw);
  });

  it("handles colons in values without breaking", () => {
    const raw = "---\nname: foo\nurl: https://example.com/x\n---\nbody\n";
    const { frontmatter } = splitFrontmatter(raw);
    expect(frontmatter.url).toBe("https://example.com/x");
  });
});

describe("loadSkill", () => {
  it("loads kb-dev and returns body + frontmatter", async () => {
    const loaded = await loadSkill("kb-dev");
    expect(loaded.name).toBe("kb-dev");
    expect(loaded.frontmatter.name).toBe("kb-dev");
    expect(loaded.body.length).toBeGreaterThan(100);
    // The kb-dev body must contain the 12-phase table — smoke test for drift.
    expect(loaded.body).toContain("Phase");
  });

  it("loads a vendor-local skill (polish)", async () => {
    const loaded = await loadSkill("polish");
    expect(loaded.name).toBe("polish");
    // Phase 1 fix: polish body must NOT contain /teach-impeccable
    expect(loaded.body).not.toContain("teach-impeccable");
  });

  it("throws for a skill that doesn't exist", async () => {
    await expect(loadSkill("nonexistent-skill")).rejects.toThrow(
      /skill not found/,
    );
  });
});

describe("loadAgent", () => {
  it("loads the orchestrator agent", async () => {
    const loaded = await loadAgent("orchestrator");
    expect(loaded.frontmatter.name).toBe("orchestrator");
    expect(loaded.frontmatter.model).toBe("opus");
    expect(loaded.body).toContain("NIU");
  });

  it("loads the frontend-engineer agent", async () => {
    const loaded = await loadAgent("frontend-engineer");
    expect(loaded.frontmatter.name).toBe("frontend-engineer");
    expect(loaded.frontmatter.model).toBe("sonnet");
  });
});
