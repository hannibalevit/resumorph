// Popular, single-purpose consumer sites that are never job postings or application
// forms. Scanning, field-answer generation, and the inline "AI" button are all
// disabled on these hostnames (and their subdomains) regardless of the extension's
// enabled/disabled toggle.
//
// Used by the background and sidepanel entries (module contexts). Content scripts
// use the duplicated copy at content/blockedSites.ts instead — see the note there
// for why. Keep both lists in sync.
export const BLOCKED_HOSTNAMES = [
  "facebook.com",
  "instagram.com",
  "youtube.com",
  "youtu.be",
  "tiktok.com",
  "twitter.com",
  "x.com",
  "reddit.com",
  "pinterest.com",
  "snapchat.com",
  "whatsapp.com",
  "telegram.org",
  "discord.com",
  "twitch.tv",
  "netflix.com",
  "hulu.com",
  "disneyplus.com",
  "spotify.com",
  "soundcloud.com",
  "amazon.com",
  "ebay.com",
  "aliexpress.com",
  "wikipedia.org",
];

function normalizeHostname(hostname: string): string {
  return hostname.toLowerCase().replace(/^www\./, "");
}

export function isBlockedHostname(hostname: string | undefined | null): boolean {
  if (!hostname) return false;
  const normalized = normalizeHostname(hostname);
  return BLOCKED_HOSTNAMES.some((domain) => normalized === domain || normalized.endsWith(`.${domain}`));
}

export function isBlockedUrl(url: string | undefined | null): boolean {
  if (!url) return false;
  try {
    return isBlockedHostname(new URL(url).hostname);
  } catch {
    return false;
  }
}
