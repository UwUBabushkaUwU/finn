export interface MetaSection {
  company_name?: string;
  generated_at?: string;
  documents_used?: Array<{
    url: string;
    kind: string; // 'transcript' | 'presentation' | 'annual_report'
    period: string; // 'Q1 FY26', 'FY26', etc.
  }>;
}

export interface PromiseTarget {
  id: string;
  metric?: string;
  segment?: string | null;
  evolution?: string;
  statement?: string;
  applies_to?: string;
  revision_label?: string;
}

export interface PromiseVerdict {
  id: string;
  made_in?: string;
  promise: string;
  verdict: string;
  evidence: string;
  applies_to?: string;
  evidence_ids?: string[];
  revision_label?: string;
}

export interface PromiseSourceItem {
  id: string;
  kind?: string;
  page?: number | null;
  quote?: string;
  period?: string;
  speaker?: string;
  document_id?: string;
}

export interface PromisesSection {
  read?: string;
  counts?: string;
  targets?: PromiseTarget[];
  verdicts?: PromiseVerdict[];
  total_promises?: number;
  overrides_count?: number;
}

export interface GuidanceTimelineSection {
  timeline?: string[];
}

export interface NumbersFlag {
  flag: string;
  triggered: boolean;
  value?: number;
  threshold?: number;
  details?: string;
  note?: string;
  numbers?: Record<string, unknown>;
}

export interface NumbersSection {
  basis?: string;
  is_lender?: boolean;
  snapshot?: {
    ttm_pat?: {
      value?: number | null;
      unit?: string;
      yoy_growth_pct?: number | null;
      source?: Record<string, unknown>;
    };
    ttm_revenue?: { value?: number | null; unit?: string; source?: Record<string, unknown> };
    latest_quarter_pat?: {
      value?: number | null;
      unit?: string;
      quarter?: string;
      yoy_growth_pct?: number | null;
    };
    latest_quarter_revenue?: {
      value?: number | null;
      unit?: string;
      quarter?: string;
      yoy_growth_pct?: number | null;
    };
    latest_operating_margin?: {
      value?: number | null;
      unit?: string;
      quarter?: string;
      note?: string;
    };
  };
  balance_sheet?: {
    borrowings?: { value?: number | null; unit?: string };
    debt_to_equity?: { value?: number | null; note?: string };
    working_capital_days?: { value?: number | null; unit?: string };
    cash_conversion_cycle_days?: { value?: number | null; unit?: string };
  };
  cash_quality?: {
    cash_conversion_3y?: {
      percentage?: number | null;
      sum_cfo?: number | null;
      sum_pat?: number | null;
    };
  };
  flags?: NumbersFlag[];
  trajectory?: Record<string, { value: number; unit?: string }>;
}

export interface SnapshotSegment {
  name: string;
  share_of_revenue?: number | null;
  page?: number | null;
}

export interface SnapshotSection {
  what_it_does?: string;
  segments?: SnapshotSegment[];
  customers_and_markets?: string;
  pages_used?: number[];
}

export interface BullBearItem {
  point: string;
  ids: string[];
}

export interface BullBearSection {
  bull?: BullBearItem[];
  bear?: BullBearItem[];
}

export interface FinancialsTable {
  columns: string[];
  rows: Array<{
    label: string;
    values: Array<number | null>;
  }>;
}

export interface FinancialsRow {
  ticker: string;
  basis: string;
  tables: {
    quarterly_results?: FinancialsTable;
    profit_loss?: FinancialsTable;
    balance_sheet?: FinancialsTable;
    cash_flow?: FinancialsTable;
    ratios?: FinancialsTable;
  };
}

export type VerdictGroup = "kept" | "broken" | "in_progress" | "too_early" | "cant_verify";

export function mapVerdictToGroup(verdict: string): VerdictGroup {
  const norm = verdict.toLowerCase().trim();
  if (norm === "delivered" || norm === "likely_delivered" || norm === "ended + ahead") {
    return "kept";
  }
  if (norm === "missed" || norm === "likely_missed" || norm === "partly") {
    return "broken";
  }
  if (norm === "on_track" || norm === "ahead" || norm === "behind") {
    return "in_progress";
  }
  if (norm === "pending") {
    return "too_early";
  }
  // unverifiable, not_judged, etc.
  return "cant_verify";
}

export function formatVerdictChip(verdict: string): {
  label: string;
  isLikely: boolean;
  group: VerdictGroup;
  colorClass: string;
} {
  const norm = verdict.toLowerCase().trim();
  const group = mapVerdictToGroup(norm);
  const isLikely = norm.startsWith("likely_");

  if (norm === "delivered") {
    return { label: "Kept", isLikely: false, group, colorClass: "text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/60 border-emerald-300 dark:border-emerald-800" };
  }
  if (norm === "likely_delivered") {
    return { label: "Likely kept", isLikely: true, group, colorClass: "text-emerald-700 dark:text-emerald-400 bg-transparent border-emerald-400/80 dark:border-emerald-500/80 border-dashed" };
  }
  if (norm === "ended + ahead" || norm === "ahead") {
    return { label: "Ahead", isLikely: false, group, colorClass: "text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-950/60 border-teal-300 dark:border-teal-800" };
  }
  if (norm === "missed") {
    return { label: "Broken", isLikely: false, group, colorClass: "text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/60 border-rose-300 dark:border-rose-800" };
  }
  if (norm === "likely_missed") {
    return { label: "Likely broken", isLikely: true, group, colorClass: "text-rose-700 dark:text-rose-400 bg-transparent border-rose-400/80 dark:border-rose-500/80 border-dashed" };
  }
  if (norm === "partly") {
    return { label: "Partly", isLikely: false, group, colorClass: "text-rose-600 dark:text-rose-400 bg-rose-50/50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900" };
  }
  if (norm === "behind") {
    return { label: "Behind", isLikely: false, group, colorClass: "text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60 border-amber-300 dark:border-amber-800" };
  }
  if (norm === "on_track") {
    return { label: "On track", isLikely: false, group, colorClass: "text-neutral-700 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700" };
  }
  if (norm === "above_plan" || norm === "above plan") {
    return { label: "Above plan", isLikely: false, group: "in_progress", colorClass: "text-neutral-700 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700" };
  }
  if (norm === "within_plan" || norm === "within plan") {
    return { label: "Within plan", isLikely: false, group: "in_progress", colorClass: "text-neutral-700 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700" };
  }
  if (norm === "below_plan" || norm === "below plan") {
    return { label: "Below plan", isLikely: false, group: "in_progress", colorClass: "text-neutral-700 dark:text-neutral-300 bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700" };
  }
  if (norm === "pending") {
    return { label: "Too early", isLikely: false, group, colorClass: "text-neutral-600 dark:text-neutral-400 bg-neutral-50 dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800" };
  }
  return { label: "Can't verify", isLikely: false, group, colorClass: "text-neutral-500 dark:text-neutral-400 bg-neutral-50 dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800" };
}

export function getPromiseSortPriority(verdict: string): number {
  const norm = verdict.toLowerCase().trim();
  // 1: Broken
  if (norm === "missed" || norm === "likely_missed" || norm === "partly") return 1;
  // 2: Behind
  if (norm === "behind") return 2;
  // 3: Kept / Ahead
  if (norm === "delivered" || norm === "likely_delivered" || norm === "ended + ahead" || norm === "ahead") return 3;
  // 4: On track / Neutral Capex plans
  if (norm === "on_track" || norm.includes("plan")) return 4;
  // 5: Collapsed row (too early, can't verify)
  return 5;
}

export function formatTimeAgo(isoString?: string): string {
  if (!isoString) return "Recently";
  try {
    const diffMs = Date.now() - new Date(isoString).getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours < 1) {
      const diffMins = Math.max(1, Math.floor(diffMs / (1000 * 60)));
      return `${diffMins}m ago`;
    }
    if (diffHours < 24) {
      return `${diffHours}h ago`;
    }
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return "yesterday";
    return `${diffDays}d ago`;
  } catch {
    return "recently";
  }
}

export interface RevisedGuidance {
  raw: string;
  metricLabel: string;
  steps: Array<{
    value: string;
    quarter: string;
  }>;
}

export function cleanEvidenceText(evidence?: string): string {
  if (!evidence) return "";
  let text = evidence;

  // 1. Strip internal IDs in parentheses like (N173), (R1, N32), (R15), (IDs: ['R20']), etc.
  text = text.replace(/\s*\((?:IDs:[^)]*|[A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)\)/gi, "");
  text = text.replace(/\s*\([A-Z]\d+\)/g, "");
  text = text.replace(/\s*citing\s+[A-Z]\d+\b/gi, "");

  // 2. Fix broken double currency symbols like ₹1,₹600 cr or 1,₹600 cr
  text = text.replace(/₹\s*(\d+)\s*,\s*₹\s*(\d+)/g, "₹$1,$2");
  text = text.replace(/(\d+)\s*,\s*₹\s*(\d+)/g, "₹$1,$2");
  text = text.replace(/₹\s*₹+/g, "₹");

  // Prepend ₹ on every amount in cr/crores strictly before the number, never inside
  text = text.replace(/(^|[^\d₹$,])(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\s*(?:cr|crores)\b/gi, "$1₹$2 cr");
  text = text.replace(/(^|[^\d₹$,])(\d{1,3}(?:,\d{2,3})*)–(\d{1,3}(?:,\d{2,3})*)\s*(?:cr|crores)\b/gi, "$1₹$2–$3 cr");
  text = text.replace(/₹\s*₹+/g, "₹");

  // 3. Ensure "at current run-rate" on run-rate evidence
  if (/\brun-rate\b/i.test(text) && !/at current run-rate/i.test(text)) {
    text = text.replace(/\b(?:revenue\s+)?run-rate(?:\s+is)?/gi, "revenue at current run-rate:");
  }

  // 4. Format percentages to 1 decimal if they have 2+ decimals
  text = text.replace(/(\d+\.\d{2,})%/g, (_, num) => `${parseFloat(num).toFixed(1)}%`);

  // 5. Clean up whitespace
  text = text.replace(/\s+/g, " ").trim();
  text = text.replace(/\s+([.,;:])/g, "$1");

  return text;
}

function formatGuidanceUnits(val: string): string {
  let s = val.trim();

  // Unit replacements
  s = s.replace(/(\d+)units\b/gi, "$1 mn units");
  s = s.replace(/(\d+)stores\b/gi, "$1 stores");
  s = s.replace(/(\d+)\$/g, "$$$1B");
  s = s.replace(/(\d+)x\b/gi, "$1×");

  // Currency: clean double symbols and format
  s = s.replace(/₹\s*(\d+)\s*,\s*₹\s*(\d+)/g, "₹$1,$2");
  s = s.replace(/(\d+)\s*,\s*₹\s*(\d+)/g, "₹$1,$2");
  s = s.replace(/₹\s*₹+/g, "₹");
  s = s.replace(/(\d+(?:,\d+)*)\s*₹\s*cr/gi, "₹$1 cr");
  s = s.replace(/(^|[^\d₹$,])(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\s*(?:cr|crores)\b/gi, "$1₹$2 cr");
  s = s.replace(/₹\s*₹+/g, "₹");

  return s;
}

export function parseRevisedTimeline(timelineList: string[]): RevisedGuidance[] {
  const revised: RevisedGuidance[] = [];

  for (const item of timelineList) {
    if (!item.includes("→") && !item.includes("->")) {
      continue;
    }

    const colonIdx = item.indexOf(":");
    let metricLabel = "";
    let rest = item;

    if (colonIdx !== -1) {
      metricLabel = item.slice(0, colonIdx).trim();
      rest = item.slice(colonIdx + 1).trim();
    }

    // Replace standard arrows
    const parts = rest.split(/→|->/).map((p) => p.trim());
    if (parts.length <= 1) continue;

    const steps: Array<{ value: string; quarter: string }> = [];

    for (const part of parts) {
      // Expected format: "26–27% (Q2 FY27)" or "Expect something. (Q4 FY26)"
      const match = part.match(/^(.*?)(?:\s*\((Q[1-4]\s+FY\d{2,4}|FY\d{2,4})\))?$/i);
      const val = match ? match[1]?.trim() : part;
      const qtr = match ? match[2]?.trim() || "" : "";

      // Only include numeric values (contains digits)
      if (val && /\d/.test(val)) {
        steps.push({
          value: formatGuidanceUnits(val),
          quarter: qtr,
        });
      }
    }

    // Rule: ONLY chains of 2+ numeric values of the same metric, segment and period.
    if (steps.length < 2) {
      continue;
    }

    // Rule: “How the story changed” ONLY shows chains where the value actually changed.
    const normalizedValues = new Set(
      steps.map((s) => s.value.replace(/[\s₹$cr–-]+/gi, "").toLowerCase())
    );
    if (normalizedValues.size < 2) {
      // Values are identical across all steps (no actual change)
      continue;
    }

    // Beautify metric label e.g. "FY27 revenue_growth" -> "FY27 revenue growth"
    const cleanedLabel = metricLabel.replace(/_/g, " ");

    revised.push({
      raw: item,
      metricLabel: cleanedLabel || "Target Revision",
      steps,
    });
  }

  return revised;
}

export function findDocumentUrl(
  period?: string,
  kind?: string,
  documentsUsed?: Array<{ url: string; kind: string; period: string }>
): string | undefined {
  if (!documentsUsed || documentsUsed.length === 0) return undefined;
  
  if (period && kind) {
    const doc = documentsUsed.find(
      (d) => d.kind.toLowerCase() === kind.toLowerCase() && d.period?.toLowerCase() === period.toLowerCase()
    );
    if (doc) return doc.url;
  }

  if (period) {
    const doc = documentsUsed.find((d) => d.period?.toLowerCase() === period.toLowerCase());
    if (doc) return doc.url;
  }

  if (kind) {
    const doc = documentsUsed.find((d) => d.kind.toLowerCase() === kind.toLowerCase());
    if (doc) return doc.url;
  }

  return documentsUsed[0]?.url;
}

