import { describe, expect, it } from "vitest";
import { isBlockedHostname, isBlockedUrl } from "../src/shared/blockedSites";

describe("blocked sites", () => {
  it("blocks known consumer sites and their subdomains", () => {
    expect(isBlockedHostname("youtube.com")).toBe(true);
    expect(isBlockedHostname("www.youtube.com")).toBe(true);
    expect(isBlockedHostname("m.youtube.com")).toBe(true);
  });

  it("blocks Google product subdomains but not Search or Google-hosted job pages", () => {
    expect(isBlockedHostname("mail.google.com")).toBe(true);
    expect(isBlockedHostname("docs.google.com")).toBe(true);
    expect(isBlockedHostname("www.google.com")).toBe(false);
    expect(isBlockedHostname("careers.google.com")).toBe(false);
  });

  it("blocks popular AI chat services", () => {
    expect(isBlockedHostname("chatgpt.com")).toBe(true);
    expect(isBlockedHostname("claude.ai")).toBe(true);
    expect(isBlockedHostname("gemini.google.com")).toBe(true);
  });

  it("allows regular job-board URLs and malformed input", () => {
    expect(isBlockedUrl("https://jobs.example.com/software-engineer")).toBe(false);
    expect(isBlockedUrl("not a url")).toBe(false);
  });
});
