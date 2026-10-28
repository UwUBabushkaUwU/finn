const IST_TIMEZONE = "Asia/Kolkata";

/**
 * Returns today's formatted date in IST (e.g. "Wednesday, 28 October 2026").
 */
export function getTodayFormattedIST(date = new Date()): string {
  return new Intl.DateTimeFormat("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: IST_TIMEZONE,
  }).format(date);
}

/**
 * Formats a filing's UTC timestamp:
 * - "2h ago" (or "14m ago") if filed within the last 24 hours
 * - "27 Oct, 6:07 PM" (IST) if older than 24 hours
 */
export function formatFilingTime(isoUtcString: string, referenceTime = new Date()): string {
  const filedDate = new Date(isoUtcString);
  const diffMs = referenceTime.getTime() - filedDate.getTime();

  // If under 24 hours
  if (diffMs >= 0 && diffMs < 24 * 60 * 60 * 1000) {
    const diffMins = Math.floor(diffMs / (60 * 1000));
    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    return `${diffHours}h ago`;
  }

  // Older than 24 hours: "27 Oct, 6:07 PM" in IST
  const monthFormatter = new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: IST_TIMEZONE,
  });

  const timeFormatter = new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: IST_TIMEZONE,
  });

  const datePart = monthFormatter.format(filedDate);
  const timePart = timeFormatter.format(filedDate);

  return `${datePart}, ${timePart}`;
}

/**
 * Parse time window query param ('24h' | '3d' | '7d' | '30d')
 * returns hours number and validated window string.
 */
export function parseTimeWindow(w?: string | string[]): {
  window: "24h" | "3d" | "7d" | "30d";
  hours: number;
  label: string;
} {
  const param = Array.isArray(w) ? w[0] : w;
  switch (param) {
    case "3d":
      return { window: "3d", hours: 72, label: "last 3 days" };
    case "7d":
      return { window: "7d", hours: 168, label: "last 7 days" };
    case "30d":
      return { window: "30d", hours: 720, label: "last 30 days" };
    case "24h":
    default:
      return { window: "24h", hours: 24, label: "last 24 hours" };
  }
}
