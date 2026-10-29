import { NumbersSection as NumbersData, FinancialsRow } from "@/lib/company";

interface NumbersSectionProps {
  numbers?: NumbersData | null;
  financials?: FinancialsRow | null;
}

export function NumbersSection({ numbers, financials }: NumbersSectionProps) {
  const isLender = Boolean(numbers?.is_lender);
  const snap = numbers?.snapshot;
  const bs = numbers?.balance_sheet;
  const flags = numbers?.flags || [];
  const triggeredFlags = flags.filter((f) => f.triggered);

  // 1. Tile 1: TTM Revenue
  const ttmRevVal = snap?.ttm_revenue?.value;
  const ttmRevStr = ttmRevVal != null ? `₹${ttmRevVal.toLocaleString("en-IN")} cr` : "—";

  // 2. Tile 2: TTM PAT with YoY
  const ttmPatVal = snap?.ttm_pat?.value;
  const ttmPatStr = ttmPatVal != null ? `₹${ttmPatVal.toLocaleString("en-IN")} cr` : "—";
  const patYoY = snap?.latest_quarter_pat?.yoy_growth_pct;

  // 3. Tile 3: Operating margin (latest)
  const opmVal = snap?.latest_operating_margin?.value;
  const opmQuarter = snap?.latest_operating_margin?.quarter;

  // 4. Tile 4: Debt-to-equity
  const deVal = bs?.debt_to_equity?.value;
  const borrowingsVal = bs?.borrowings?.value;

  // --- SVG Chart: Last 12 Quarters Revenue & Margin ---
  const qTable = financials?.tables?.quarterly_results;
  const rawCols = qTable?.columns || [];
  const rawRows = qTable?.rows || [];

  // Find Sales/Revenue row
  const revRow = rawRows.find((r) =>
    r.label.toLowerCase().includes("sales") || r.label.toLowerCase().includes("revenue")
  );
  // Find Margin row (OPM % or Financing Margin %)
  const marginRow = rawRows.find((r) =>
    r.label.toLowerCase().includes("opm") ||
    r.label.toLowerCase().includes("margin") ||
    r.label.toLowerCase().includes("operating profit margin")
  );

  // Last 12 quarters
  const chartLength = Math.min(12, rawCols.length);
  const startIdx = Math.max(0, rawCols.length - 12);
  const chartCols = rawCols.slice(startIdx);
  const chartRevs = revRow ? revRow.values.slice(startIdx).map((v) => v || 0) : [];
  const chartMargins = marginRow ? marginRow.values.slice(startIdx).map((v) => (v != null ? v : 0)) : [];

  const hasChartData = chartCols.length > 0 && chartRevs.length > 0;

  // SVG math
  const svgWidth = 320;
  const svgHeight = 115;
  const plotTop = 20;
  const plotBottom = 92;
  const plotHeight = plotBottom - plotTop;
  const plotLeft = 8;
  const plotRight = svgWidth - 8;
  const plotWidth = plotRight - plotLeft;

  const maxRev = chartRevs.length > 0 ? Math.max(...chartRevs) * 1.15 || 1 : 1;
  const minMargin = chartMargins.length > 0 ? Math.min(...chartMargins) : 0;
  const maxMargin = chartMargins.length > 0 ? Math.max(...chartMargins) : 10;
  const marginRange = maxMargin - minMargin || 1;

  const slotWidth = chartLength > 0 ? plotWidth / chartLength : 0;
  const barWidth = Math.max(6, Math.min(14, slotWidth - 6));

  const bars = chartRevs.map((rev, i) => {
    const x = plotLeft + i * slotWidth + (slotWidth - barWidth) / 2;
    const bHeight = Math.max(2, (rev / maxRev) * plotHeight);
    const y = plotBottom - bHeight;
    const isLatest = i === chartRevs.length - 1;
    return { x, y, width: barWidth, height: bHeight, isLatest, rev };
  });

  const linePoints = chartMargins.map((margin, i) => {
    const x = plotLeft + i * slotWidth + slotWidth / 2;
    const norm = (margin - minMargin) / marginRange;
    const y = plotBottom - norm * (plotHeight - 8);
    const isLatest = i === chartMargins.length - 1;
    return { x, y, margin, isLatest };
  });

  const linePathD = linePoints.reduce((acc, pt, i) => {
    return `${acc} ${i === 0 ? "M" : "L"} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
  }, "");

  const latestBar = bars[bars.length - 1];
  const latestPoint = linePoints[linePoints.length - 1];
  const firstQuarterLabel = chartCols[0] || "";
  const lastQuarterLabel = chartCols[chartCols.length - 1] || "";

  return (
    <section aria-labelledby="numbers-heading" className="space-y-3 pt-2">
      <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
        <h2
          id="numbers-heading"
          className="text-xs font-mono font-bold uppercase tracking-wider text-neutral-700 dark:text-neutral-300"
        >
          The Numbers
        </h2>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          Reported financials
        </span>
      </div>

      {/* Four Tiles */}
      <div className="grid grid-cols-2 gap-2">
        {/* Tile 1: TTM Revenue */}
        <div
          id="N_TTM_REV"
          className="p-2.5 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 space-y-1"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            TTM Revenue
          </div>
          <div className="text-base font-mono font-bold text-neutral-950 dark:text-neutral-50 tabular-nums">
            {ttmRevStr}
          </div>
          <div id="N_REV_LATEST" className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
            {snap?.latest_quarter_revenue?.quarter
              ? `${snap.latest_quarter_revenue.quarter}: ₹${snap.latest_quarter_revenue.value?.toLocaleString("en-IN")} cr`
              : "Consolidated"}
          </div>
        </div>

        {/* Tile 2: TTM PAT (with YoY) */}
        <div
          id="N_TTM_PAT"
          className="p-2.5 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 space-y-1"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400 flex items-center justify-between">
            <span>TTM PAT</span>
            {patYoY != null && (
              <span
                id="N_PAT_LATEST"
                className={`text-[10px] font-mono font-semibold ${
                  patYoY >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                }`}
              >
                {patYoY >= 0 ? "+" : ""}
                {patYoY.toFixed(1)}% YoY
              </span>
            )}
          </div>
          <div className="text-base font-mono font-bold text-neutral-950 dark:text-neutral-50 tabular-nums">
            {ttmPatStr}
          </div>
          <div className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
            {snap?.latest_quarter_pat?.quarter
              ? `${snap.latest_quarter_pat.quarter}: ₹${snap.latest_quarter_pat.value?.toLocaleString("en-IN")} cr`
              : "Consolidated"}
          </div>
        </div>

        {/* Tile 3: Operating Margin (latest) */}
        <div
          id="N_OPM_LATEST"
          className="p-2.5 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 space-y-1"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400 flex items-center justify-between">
            <span>{isLender ? "Financing Margin" : "Operating Margin"}</span>
            {isLender && (
              <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400">
                lender
              </span>
            )}
          </div>
          <div className="text-base font-mono font-bold text-neutral-950 dark:text-neutral-50 tabular-nums">
            {opmVal != null
              ? `${opmVal.toFixed(1)}%`
              : isLender && chartMargins.length > 0
              ? `${chartMargins[chartMargins.length - 1].toFixed(1)}%`
              : "—"}
          </div>
          <div className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
            {isLender ? "NBFC / Banking spread" : opmQuarter ? `Latest (${opmQuarter})` : "Latest reported"}
          </div>
        </div>

        {/* Tile 4: Debt-to-Equity */}
        <div
          id="N_DEBT_TO_EQUITY"
          className="p-2.5 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 space-y-1"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400 flex items-center justify-between">
            <span>{isLender ? "Borrowings" : "Debt-to-Equity"}</span>
            {isLender && (
              <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400">
                lender
              </span>
            )}
          </div>
          <div className="text-base font-mono font-bold text-neutral-950 dark:text-neutral-50 tabular-nums">
            {isLender
              ? borrowingsVal != null
                ? `₹${borrowingsVal.toLocaleString("en-IN")} cr`
                : "—"
              : deVal != null
              ? deVal.toFixed(2)
              : "—"}
          </div>
          <div id="N_BORROWINGS" className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
            {isLender ? "Reported borrowings" : borrowingsVal ? `Debt: ₹${borrowingsVal.toLocaleString("en-IN")} cr` : "Consolidated"}
          </div>
        </div>
      </div>

      {/* SVG Chart: Last 12 Quarters Revenue & Margin */}
      {hasChartData && (
        <div className="p-3 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 space-y-1">
          <div className="flex items-center justify-between text-[10px] font-mono text-neutral-500 dark:text-neutral-400">
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-2 bg-neutral-300 dark:bg-neutral-600 rounded-2xs" />
              <span>Revenue (bars)</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-0.5 bg-amber-600 dark:bg-amber-400" />
              <span>{isLender ? "Financing % (line)" : "OPM % (line)"}</span>
            </span>
          </div>

          <div className="w-full overflow-hidden">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              className="w-full h-auto text-neutral-800 dark:text-neutral-200 select-none"
            >
              {/* Baseline */}
              <line
                x1={plotLeft}
                y1={plotBottom}
                x2={plotRight}
                y2={plotBottom}
                className="stroke-neutral-200 dark:stroke-neutral-800"
                strokeWidth="1"
              />

              {/* Revenue Bars */}
              {bars.map((bar, i) => (
                <rect
                  key={`bar-${i}`}
                  x={bar.x}
                  y={bar.y}
                  width={bar.width}
                  height={bar.height}
                  rx="1"
                  className={
                    bar.isLatest
                      ? "fill-neutral-600 dark:fill-neutral-400"
                      : "fill-neutral-200/90 dark:fill-neutral-800/90"
                  }
                />
              ))}

              {/* Margin Path */}
              {linePoints.length > 1 && (
                <path
                  d={linePathD}
                  fill="none"
                  className="stroke-amber-600 dark:stroke-amber-400"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {/* Margin Points */}
              {linePoints.map((pt, i) => (
                <circle
                  key={`pt-${i}`}
                  cx={pt.x}
                  cy={pt.y}
                  r={pt.isLatest ? 3 : 1.5}
                  className={
                    pt.isLatest
                      ? "fill-amber-600 dark:fill-amber-400 stroke-white dark:stroke-neutral-900"
                      : "fill-amber-600/70 dark:fill-amber-400/70"
                  }
                  strokeWidth={pt.isLatest ? "1.5" : "0"}
                />
              ))}

              {/* Label Latest Bar Value */}
              {latestBar && (
                <text
                  x={latestBar.x + latestBar.width / 2}
                  y={Math.max(12, latestBar.y - 4)}
                  textAnchor="middle"
                  className="text-[9px] font-mono fill-neutral-700 dark:fill-neutral-300 font-bold"
                >
                  ₹{Math.round(latestBar.rev).toLocaleString("en-IN")} cr
                </text>
              )}

              {/* Label Latest Line Value */}
              {latestPoint && (
                <text
                  x={Math.min(svgWidth - 16, latestPoint.x + 4)}
                  y={latestPoint.y - 4}
                  textAnchor="start"
                  className="text-[9px] font-mono fill-amber-700 dark:fill-amber-400 font-bold"
                >
                  {latestPoint.margin.toFixed(1)}%
                </text>
              )}

              {/* Axis Quarter Labels: First & Last */}
              <text
                x={plotLeft}
                y={svgHeight - 4}
                textAnchor="start"
                className="text-[9px] font-mono fill-neutral-400 dark:fill-neutral-500"
              >
                {firstQuarterLabel}
              </text>
              <text
                x={plotRight}
                y={svgHeight - 4}
                textAnchor="end"
                className="text-[9px] font-mono fill-neutral-500 dark:fill-neutral-400 font-medium"
              >
                {lastQuarterLabel}
              </text>
            </svg>
          </div>
        </div>
      )}

      {/* Flags Section */}
      <div className="space-y-1.5">
        <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
          Balance-sheet & Cash flags
        </div>

        {triggeredFlags.length > 0 ? (
          <div className="space-y-1.5">
            {triggeredFlags.map((flag, idx) => (
              <div
                key={idx}
                id={`N_FLAG_${idx + 1}`}
                className="p-2 rounded border border-rose-200 dark:border-rose-900/60 bg-rose-50/60 dark:bg-rose-950/40 text-xs font-mono text-rose-800 dark:text-rose-300 space-y-0.5"
              >
                <div className="font-bold flex items-center gap-1.5">
                  <span className="text-rose-600 dark:text-rose-400">⚠</span>
                  <span className="uppercase tracking-tight">{flag.flag.replace(/_/g, " ")}</span>
                </div>
                <div className="text-[11px] leading-relaxed text-rose-900/90 dark:text-rose-200/90">
                  {flag.details || `Triggered threshold (${flag.threshold}) with value ${flag.value}`}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div
            id="N_NO_FLAGS"
            className="p-2 rounded border border-neutral-200 dark:border-neutral-800 bg-neutral-50/60 dark:bg-neutral-900/30 text-xs font-mono text-neutral-600 dark:text-neutral-400 flex items-center gap-1.5"
          >
            <span className="text-emerald-600 dark:text-emerald-400 select-none">✓</span>
            <span>No balance-sheet or cash flags.</span>
          </div>
        )}
      </div>

      {/* Hidden Anchors for bull/bear references like N_CCC_DAYS, N_WC_DAYS, N_CASH_CONV_3Y */}
      <div className="hidden" aria-hidden="true">
        <span id="N_CCC_DAYS">{bs?.cash_conversion_cycle_days?.value}</span>
        <span id="N_WC_DAYS">{bs?.working_capital_days?.value}</span>
        <span id="N_CASH_CONV_3Y">{numbers?.cash_quality?.cash_conversion_3y?.percentage}</span>
      </div>
    </section>
  );
}
