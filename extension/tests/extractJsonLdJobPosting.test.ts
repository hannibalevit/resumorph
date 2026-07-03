import { beforeEach, describe, expect, it } from "vitest";
import { extractJsonLdJobPosting, hasJsonLdJobPosting } from "../src/content/jobExtraction/extractJsonLdJobPosting";

const longDescription = [
  "We are hiring a senior product engineer to build reliable browser tooling for job seekers.",
  "The role includes TypeScript, React, API integration, accessibility, observability, and careful user-facing polish.",
  "You will collaborate with design and backend engineers, improve extraction quality, and maintain a high quality bar.",
  "Candidates should be comfortable shipping independently, reviewing code, testing critical flows, and simplifying complex UI states.",
].join(" ");

describe("JSON-LD job extraction", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("extracts high-signal fields from JobPosting JSON-LD", () => {
    document.body.innerHTML = `
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Senior Product Engineer",
          "description": "<p>${longDescription}</p>",
          "datePosted": "2026-07-01",
          "employmentType": "FULL_TIME",
          "hiringOrganization": { "name": "Resume Tailor Labs" },
          "jobLocation": {
            "address": {
              "addressLocality": "Tbilisi",
              "addressCountry": "GE"
            }
          },
          "baseSalary": {
            "currency": "USD",
            "value": {
              "minValue": 100000,
              "maxValue": 130000,
              "unitText": "YEAR"
            }
          }
        }
      </script>
    `;

    const result = extractJsonLdJobPosting();

    expect(hasJsonLdJobPosting()).toBe(true);
    expect(result?.detected).toMatchObject({
      jobTitle: "Senior Product Engineer",
      company: "Resume Tailor Labs",
      location: "Tbilisi, GE",
      employmentType: "FULL_TIME",
      salary: "USD 100000-130000 YEAR",
    });
    expect(result?.cleanedText).toContain("Date posted: 2026-07-01");
  });

  it("ignores invalid JSON-LD scripts", () => {
    document.body.innerHTML = '<script type="application/ld+json">{bad json</script>';

    expect(hasJsonLdJobPosting()).toBe(false);
    expect(extractJsonLdJobPosting()).toBeNull();
  });
});
