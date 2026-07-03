import type { ExtractedJobPage } from "./types";
import { cleanWhitespace, stripHtml, truncateText } from "./extractVisibleText";

type JsonValue = null | string | number | boolean | JsonValue[] | { [key: string]: JsonValue };
type JsonObject = { [key: string]: JsonValue };

function asObject(value: JsonValue | undefined): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function asString(value: JsonValue | undefined): string | undefined {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return undefined;
}

function isJobPosting(value: JsonObject): boolean {
  const type = value["@type"];
  if (typeof type === "string") {
    return type.toLowerCase() === "jobposting";
  }
  return Array.isArray(type) && type.some((item) => String(item).toLowerCase() === "jobposting");
}

function walk(value: JsonValue, results: JsonObject[]): void {
  if (!value || typeof value !== "object") {
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item) => walk(item, results));
    return;
  }

  if (isJobPosting(value)) {
    results.push(value);
  }

  const graph = value["@graph"];
  if (graph) {
    walk(graph, results);
  }

  Object.values(value).forEach((nested) => walk(nested, results));
}

function parseJsonLdScripts(): JsonObject[] {
  const jobs: JsonObject[] = [];

  document.querySelectorAll("script[type='application/ld+json']").forEach((script) => {
    const text = script.textContent?.trim();
    if (!text) {
      return;
    }

    try {
      walk(JSON.parse(text) as JsonValue, jobs);
    } catch {
      // Invalid JSON-LD is common on job boards; ignore and continue.
    }
  });

  return jobs;
}

function locationToString(value: JsonValue | undefined): string | undefined {
  if (!value) {
    return undefined;
  }

  if (Array.isArray(value)) {
    return value.map(locationToString).filter(Boolean).join("; ") || undefined;
  }

  const object = asObject(value);
  if (!object) {
    return asString(value);
  }

  const address = asObject(object.address);
  if (!address) {
    return asString(object.name);
  }

  return [address.addressLocality, address.addressRegion, address.addressCountry]
    .map(asString)
    .filter(Boolean)
    .join(", ") || undefined;
}

function salaryToString(value: JsonValue | undefined): string | undefined {
  const object = asObject(value);
  if (!object) {
    return asString(value);
  }

  const valueObject = asObject(object.value);
  const amount = valueObject ? asString(valueObject.value) : asString(object.value);
  const min = valueObject ? asString(valueObject.minValue) : undefined;
  const max = valueObject ? asString(valueObject.maxValue) : undefined;
  const currency = valueObject ? asString(valueObject.currency) : asString(object.currency);
  const unit = valueObject ? asString(valueObject.unitText) : undefined;

  if (min || max) {
    return cleanWhitespace(`${currency ?? ""} ${min ?? ""}-${max ?? ""} ${unit ?? ""}`);
  }

  return cleanWhitespace(`${currency ?? ""} ${amount ?? ""} ${unit ?? ""}`) || undefined;
}

export function extractJsonLdJobPosting(): Partial<ExtractedJobPage> | null {
  const [job] = parseJsonLdScripts();
  if (!job) {
    return null;
  }

  const organization = asObject(job.hiringOrganization);
  const description = stripHtml(asString(job.description) ?? "");
  const datePosted = asString(job.datePosted);
  const cleanedText = truncateText(
    [description, datePosted ? `Date posted: ${datePosted}` : ""].filter(Boolean).join("\n\n"),
  );

  if (cleanedText.length < 300) {
    return null;
  }

  return {
    source: "json_ld_job_posting",
    confidence: 0.9,
    detected: {
      jobTitle: asString(job.title),
      company: asString(organization?.name),
      location: locationToString(job.jobLocation),
      employmentType: asString(job.employmentType),
      salary: salaryToString(job.baseSalary),
    },
    sections: {
      description: cleanedText,
    },
    rawText: description,
    cleanedText,
    debug: {
      textLength: cleanedText.length,
      jsonLdFound: true,
      warnings: [],
    },
  };
}

export function hasJsonLdJobPosting(): boolean {
  return parseJsonLdScripts().length > 0;
}

/**
 * Reads the high-signal identity fields (company, title, location) from the first
 * JSON-LD JobPosting without the ≥300-char description gate that
 * `extractJsonLdJobPosting` applies. The company name in particular is frequently
 * present in structured data even when the visible job body never repeats it.
 */
export function readJsonLdMeta(): { company?: string; jobTitle?: string; location?: string } {
  const [job] = parseJsonLdScripts();
  if (!job) {
    return {};
  }

  const organization = asObject(job.hiringOrganization);
  return {
    company: asString(organization?.name),
    jobTitle: asString(job.title),
    location: locationToString(job.jobLocation),
  };
}
