import { describe, expect, it } from "vitest";
import { isBlockedHostname, isBlockedUrl } from "../src/shared/blockedSites";

describe("blocked sites", () => {
  it("blocks known consumer sites and their subdomains", () => {
    expect(isBlockedHostname("youtube.com")).toBe(true);
    expect(isBlockedHostname("www.youtube.com")).toBe(true);
    expect(isBlockedHostname("m.youtube.com")).toBe(true);
  });

  it("allows regular job-board URLs and malformed input", () => {
    expect(isBlockedUrl("https://jobs.example.com/software-engineer")).toBe(false);
    expect(isBlockedUrl("not a url")).toBe(false);
  });
});
