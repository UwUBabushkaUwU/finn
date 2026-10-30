import { SnapshotSection, MetaSection, findDocumentUrl } from "@/lib/company";

interface BusinessSnapshotProps {
  snapshot?: SnapshotSection | null;
  meta?: MetaSection | null;
}

export function BusinessSnapshot({ snapshot, meta }: BusinessSnapshotProps) {
  if (!snapshot) return null;

  const { what_it_does, segments = [], customers_and_markets, pages_used = [] } = snapshot;

  const hasWhatItDoes = Boolean(
    what_it_does && what_it_does.trim() && what_it_does.trim().toLowerCase() !== "none"
  );
  const hasSegments = segments.length > 0 && segments.some((s) => s.share_of_revenue != null);
  const hasCustomers = Boolean(
    customers_and_markets &&
      customers_and_markets.trim() &&
      customers_and_markets.trim().toLowerCase() !== "none"
  );

  if (!hasWhatItDoes && !hasSegments && !hasCustomers) return null;

  // Annual report link resolution
  const annualReport = meta?.documents_used?.find((d) => d.kind === "annual_report");
  const arPeriod = annualReport?.period || "FY26";
  const arUrl = annualReport?.url || findDocumentUrl(arPeriod, "annual_report", meta?.documents_used);

  // Pages string
  const pagesList =
    pages_used.length > 0
      ? pages_used.slice(0, 3).join(", ")
      : segments[0]?.page != null
      ? `${segments[0].page}`
      : "12";
  const arFirstPage = pages_used[0] || segments[0]?.page || 1;
  const arLinkWithPage = arUrl ? `${arUrl}#page=${arFirstPage}` : undefined;

  // Segment colors
  const segmentColors = [
    "bg-neutral-800 dark:bg-neutral-200 text-neutral-900 dark:text-neutral-100",
    "bg-amber-600 dark:bg-amber-500 text-amber-700 dark:text-amber-400",
    "bg-teal-600 dark:bg-teal-400 text-teal-700 dark:text-teal-300",
    "bg-indigo-600 dark:bg-indigo-400 text-indigo-700 dark:text-indigo-300",
    "bg-rose-600 dark:bg-rose-400 text-rose-700 dark:text-rose-300",
    "bg-neutral-400 dark:bg-neutral-600 text-neutral-600 dark:text-neutral-300",
  ];

  return (
    <section aria-labelledby="business-snapshot-heading" className="space-y-3 pt-2">
      <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
        <h2
          id="business-snapshot-heading"
          className="text-xs font-mono font-bold uppercase tracking-wider text-neutral-700 dark:text-neutral-300"
        >
          What the business is
        </h2>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          Primary filing overview
        </span>
      </div>

      {/* What it does */}
      {hasWhatItDoes && (
        <div id="S_WHAT" className="text-xs leading-relaxed text-neutral-800 dark:text-neutral-200 font-sans">
          {what_it_does}
        </div>
      )}

      {/* Segments Stacked Bar */}
      {hasSegments && (
        <div className="space-y-2 pt-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Revenue by segment
          </div>

          {/* Stacked bar */}
          <div
            role="img"
            aria-label="Revenue segment shares"
            className="h-3 w-full rounded-sm overflow-hidden flex bg-neutral-200 dark:bg-neutral-800"
          >
            {segments.map((seg, idx) => {
              const share = seg.share_of_revenue || 0;
              const colorClass = segmentColors[idx % segmentColors.length].split(" ")[0];
              return (
                <div
                  key={idx}
                  style={{ width: `${share}%` }}
                  title={`${seg.name}: ${share}%`}
                  className={`h-full ${colorClass} transition-all border-r border-background/20 last:border-0`}
                />
              );
            })}
          </div>

          {/* Segments legend */}
          <div className="grid grid-cols-1 gap-1.5 pt-0.5">
            {segments.map((seg, idx) => {
              const share = seg.share_of_revenue != null ? `${Math.round(seg.share_of_revenue)}%` : "—";
              const colorClass = segmentColors[idx % segmentColors.length].split(" ")[0];
              return (
                <div
                  key={idx}
                  id={`S_SEG_${idx + 1}`}
                  className="flex items-center justify-between text-xs font-mono py-0.5 border-b border-neutral-100 dark:border-neutral-800/60 last:border-0"
                >
                  <div className="flex items-center gap-2 min-w-0 pr-2">
                    <span className={`w-2 h-2 rounded-2xs shrink-0 ${colorClass}`} />
                    <span className="truncate text-neutral-800 dark:text-neutral-200 font-medium">
                      {seg.name}
                    </span>
                  </div>
                  <span className="shrink-0 font-bold text-neutral-900 dark:text-neutral-100 tabular-nums">
                    {share}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Customers and Markets (only when content exists) */}
      {hasCustomers && (
        <div id="S_CUSTOMERS" className="space-y-1 pt-1">
          <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Customers & Markets
          </div>
          <p className="text-xs leading-relaxed text-neutral-700 dark:text-neutral-300">
            {customers_and_markets}
          </p>
        </div>
      )}

      {/* Annual report link footer */}
      <div className="pt-1 text-[11px] font-mono text-neutral-500 dark:text-neutral-400">
        {arLinkWithPage ? (
          <a
            href={arLinkWithPage}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-neutral-600 dark:text-neutral-300 hover:text-black dark:hover:text-white underline decoration-neutral-300 dark:decoration-neutral-700"
          >
            <span>
              From the {arPeriod} annual report, p.{pagesList}
            </span>
            <span className="text-[10px]">↗</span>
          </a>
        ) : (
          <span>From the {arPeriod} annual report, p.{pagesList}</span>
        )}
      </div>
    </section>
  );
}
