// Local copy of ../shared/blockedSites.ts. Content scripts are loaded as classic
// (non-module) scripts via manifest.json, so they can't have a static `import` of a
// module that's also imported by other entry points — Vite would hoist it into a
// shared chunk and emit an `import` statement, which fails to load as a content
// script. Keep this duplicated rather than imported; update both if the list changes.
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
  "mail.google.com",
  "drive.google.com",
  "docs.google.com",
  "sheets.google.com",
  "slides.google.com",
  "forms.google.com",
  "calendar.google.com",
  "meet.google.com",
  "photos.google.com",
  "maps.google.com",
  "translate.google.com",
  "news.google.com",
  "play.google.com",
  "chatgpt.com",
  "chat.openai.com",
  "openai.com",
  "claude.ai",
  "anthropic.com",
  "gemini.google.com",
  "bard.google.com",
  "perplexity.ai",
  "poe.com",
  "character.ai",
  "copilot.microsoft.com",
  "you.com",
  "huggingface.co",
  "x.ai",
  "grok.com",
  "meta.ai",
  "mistral.ai",
  "deepseek.com",
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
