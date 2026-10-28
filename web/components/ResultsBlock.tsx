import { ResultsEnrichment, ResultsMetric } from "@/lib/types";

interface ResultsBlockProps {
  results: ResultsEnrichment;
  isAlso?: boolean;
}

function formatChange(pct?: number | null, label?: string | null) {
  if (label) {
    if (label.toLowerCase().includes("profitable")) {
      return (
        <span className="text-emerald-600 dark:text-emerald-400 font-medium">
          from loss
        </span>
      );
    }
    if (label.toLowerCase().includes("loss")) {
      return (
        <span className="text-red-600 dark:text-red-400 font-medium">
          to loss
        </span>
      );
    }
    return <span className="text-neutral-400 dark:text-neutral-500">{label}</span>;
  }
  if (pct == null) {
    return <span className="text-neutral-400 dark:text-neutral-500">—</span>;
  }
  if (pct > 0) {
    return (
      <span className="text-emerald-600 dark:text-emerald-400 font-medium">
        +{pct.toFixed(1)}%
      </span>
    );
  }
  if (pct < 0) {
    return (
      <span className="text-red-600 dark:text-red-400 font-medium">
        −{Math.abs(pct).toFixed(1)}%
      </span>
    );
  }
  return <span className="text-neutral-500 dark:text-neutral-400">0.0%</span>;
}

function MetricRow({
  label,
  metric,
  isLender,
  isEbitda,
}: {
  label: string;
  metric?: ResultsMetric;
  isLender?: boolean;
  isEbitda?: boolean;
}) {
  if (isLender && isEbitda) {
    return (
      <tr className="border-b border-neutral-100 dark:border-neutral-800/80">
        <td className="py-1 pr-2 text-left font-medium text-neutral-600 dark:text-neutral-400">
          {label}
        </td>
        <td className="py-1 px-2 text-right font-mono text-neutral-400 dark:text-neutral-500">
          —
        </td>
        <td className="py-1 px-2 text-right font-mono text-neutral-400 dark:text-neutral-500">
          —
        </td>
        <td className="py-1 pl-2 text-right font-mono text-neutral-400 dark:text-neutral-500">
          —
        </td>
      </tr>
    );
  }

  const currStr =
    metric?.current != null
      ? metric.current.toLocaleString("en-IN", {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        })
      : "—";

  return (
    <tr className="border-b border-neutral-100 dark:border-neutral-800/80">
      <td className="py-1 pr-2 text-left font-medium text-neutral-700 dark:text-neutral-300">
        {label}
      </td>
      <td className="py-1 px-2 text-right font-mono text-neutral-900 dark:text-neutral-100">
        {currStr}
      </td>
      <td className="py-1 px-2 text-right font-mono">
        {formatChange(metric?.qoq_pct, metric?.qoq_label)}
      </td>
      <td className="py-1 pl-2 text-right font-mono">
        {formatChange(metric?.yoy_pct, metric?.yoy_label)}
      </td>
    </tr>
  );
}

export function ResultsBlock({ results, isAlso = false }: ResultsBlockProps) {
  const metrics = results.metrics || {};
  const isLender = Boolean(results.is_lender);
  const ebitda = metrics.ebitda;

  // Header quarter label if "Also: Q2 results"
  const qMatch = results.periods?.current?.match(/Q[1-4]/i);
  const qLabel = qMatch ? qMatch[0].toUpperCase() : "Q2";

  // EBITDA margin line
  let marginLine = "";
  if (isLender) {
    marginLine = "EBITDA margin —";
  } else if (ebitda?.margin_pct != null) {
    const mVal = ebitda.margin_pct.toFixed(1);
    const mChg = ebitda.margin_change_pp;
    if (mChg != null) {
      const sign = mChg >= 0 ? "+" : "−";
      marginLine = `EBITDA margin ${mVal}% · ${sign}${Math.abs(mChg).toFixed(1)} pt YoY`;
    } else {
      marginLine = `EBITDA margin ${mVal}%`;
    }
  }

  // Footer metadata
  const basis = results.basis
    ? results.basis.charAt(0).toUpperCase() + results.basis.slice(1)
    : "Consolidated";
  const pageStr = results.page ? ` p.${results.page}` : "";
  const needsCheck = results.check === true || results.verified === false;

  return (
    <div className="mt-2.5 p-2.5 rounded bg-neutral-50/80 dark:bg-neutral-800/40 border border-neutral-200/80 dark:border-neutral-800 text-xs">
      {isAlso && (
        <div className="text-[10px] font-mono uppercase font-bold tracking-wider text-neutral-500 dark:text-neutral-400 mb-1.5 pb-1 border-b border-neutral-200/60 dark:border-neutral-800">
          Also: {qLabel} results
        </div>
      )}

      {/* 4-Row Table */}
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500 border-b border-neutral-200 dark:border-neutral-800">
            <th className="py-1 pr-2 text-left font-semibold">Metric</th>
            <th className="py-1 px-2 text-right font-semibold">This Qtr (₹ cr)</th>
            <th className="py-1 px-2 text-right font-semibold">QoQ %</th>
            <th className="py-1 pl-2 text-right font-semibold">YoY %</th>
          </tr>
        </thead>
        <tbody>
          <MetricRow label="Revenue" metric={metrics.revenue} isLender={isLender} />
          <MetricRow label="EBITDA" metric={metrics.ebitda} isLender={isLender} isEbitda={true} />
          <MetricRow label="PBT" metric={metrics.pbt} isLender={isLender} />
          <MetricRow label="PAT" metric={metrics.pat} isLender={isLender} />
        </tbody>
      </table>

      {/* EBITDA Margin line */}
      {marginLine && (
        <div className="mt-2 text-[11px] font-mono text-neutral-600 dark:text-neutral-400">
          {marginLine}
        </div>
      )}

      {/* Footer line */}
      <div className="mt-1.5 pt-1.5 border-t border-neutral-200/60 dark:border-neutral-800 flex flex-wrap items-center gap-x-1.5 text-[10px] font-mono text-neutral-500 dark:text-neutral-400">
        <span>{basis}</span>
        <span>·</span>
        {results.source_pdf_url ? (
          <a
            href={results.source_pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="underline decoration-neutral-300 dark:decoration-neutral-600 hover:text-neutral-900 dark:hover:text-neutral-200"
          >
            from results PDF{pageStr} ↗
          </a>
        ) : (
          <span>from results PDF{pageStr}</span>
        )}

        {needsCheck && (
          <>
            <span>·</span>
            <span className="text-amber-600 dark:text-amber-500 font-medium">
              figures need a check
            </span>
          </>
        )}

        {isLender && (
          <>
            <span>·</span>
            <span className="italic text-neutral-400 dark:text-neutral-500">
              EBITDA not meaningful for lenders
            </span>
          </>
        )}
      </div>
    </div>
  );
}
