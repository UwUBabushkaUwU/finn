import Link from "next/link";
import { Company, Price } from "@/lib/types";
import { MetaSection, formatTimeAgo } from "@/lib/company";

interface CompanyHeaderProps {
  ticker: string;
  company?: Company | null;
  meta?: MetaSection | null;
  price?: Price | null;
}

export function CompanyHeader({ ticker, company, meta, price }: CompanyHeaderProps) {
  const companyName = meta?.company_name || company?.name || ticker;
  const sector = company?.sector;

  // Documents summary
  const docs = meta?.documents_used || [];
  const transcriptCount = docs.filter((d) => d.kind === "transcript").length;
  const annualReport = docs.find((d) => d.kind === "annual_report");
  const arPeriod = annualReport?.period || "FY26";

  const callsLabel = transcriptCount === 1 ? "1 earnings call" : `${transcriptCount} earnings calls`;
  const timeAgoStr = formatTimeAgo(meta?.generated_at);

  const priceVal = price?.close != null ? price.close.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : null;
  const pctChange = price?.pct_change;
  const isPositive = pctChange != null && pctChange > 0;
  const isNegative = pctChange != null && pctChange < 0;

  return (
    <header className="border-b border-neutral-200 dark:border-neutral-800 pb-3 space-y-2">
      {/* Back to Brief */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100 transition-colors"
        >
          <span>←</span>
          <span>FINN Brief</span>
        </Link>
        <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400 dark:text-neutral-500">
          Primary Research
        </span>
      </div>

      {/* Main identity row */}
      <div className="flex items-baseline justify-between gap-3 pt-0.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h1 className="text-xl font-mono font-bold tracking-tight text-neutral-950 dark:text-neutral-50">
              {ticker}
            </h1>
            <span className="text-sm text-neutral-700 dark:text-neutral-300 font-medium truncate">
              {companyName}
            </span>
            {sector && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-neutral-200 dark:border-neutral-800 text-neutral-500 dark:text-neutral-400 bg-neutral-100/60 dark:bg-neutral-800/60">
                {sector}
              </span>
            )}
          </div>
        </div>

        {/* Price & Day % */}
        {priceVal && (
          <div className="text-right shrink-0">
            <div className="text-sm font-mono font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">
              ₹{priceVal}
            </div>
            {pctChange != null && (
              <div
                className={`text-[11px] font-mono tabular-nums font-medium ${
                  isPositive
                    ? "text-emerald-600 dark:text-emerald-400"
                    : isNegative
                    ? "text-rose-600 dark:text-rose-400"
                    : "text-neutral-500"
                }`}
              >
                {isPositive ? "▲ +" : isNegative ? "▼ " : ""}
                {pctChange.toFixed(2)}%
              </div>
            )}
          </div>
        )}
      </div>

      {/* Provenance quiet line */}
      <div className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400 tracking-tight">
        Researched {timeAgoStr} · {callsLabel} · {arPeriod} annual report
      </div>
    </header>
  );
}

