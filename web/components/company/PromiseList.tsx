"use client";

import { useState, useEffect } from "react";
import {
  PromiseVerdict,
  PromiseSourceItem,
  MetaSection,
  formatVerdictChip,
  getPromiseSortPriority,
  findDocumentUrl,
  cleanEvidenceText,
} from "@/lib/company";

interface PromiseListProps {
  verdicts: PromiseVerdict[];
  sources?: PromiseSourceItem[];
  meta?: MetaSection | null;
  initialExpandedId?: string;
}

export function PromiseList({ verdicts, sources = [], meta, initialExpandedId }: PromiseListProps) {
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>(() => {
    return initialExpandedId ? { [initialExpandedId]: true } : {};
  });
  const [showBottomGroup, setShowBottomGroup] = useState(false);

  // Check URL hash on client mount (e.g. #T12)
  useEffect(() => {
    if (typeof window !== "undefined") {
      const hash = window.location.hash.replace("#", "");
      if (hash && hash.startsWith("T")) {
        setExpandedIds((prev) => ({ ...prev, [hash]: true }));
        const el = document.getElementById(hash);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    }
  }, []);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Build sources lookup by id
  const sourcesById: Record<string, PromiseSourceItem> = {};
  for (const s of sources) {
    if (s.id && !sourcesById[s.id]) {
      sourcesById[s.id] = s;
    }
  }

  // Partition into main prioritized list and bottom collapsed list
  // Priority 1: Broken, Priority 2: Behind, Priority 3: Kept/Ahead, Priority 4: On track
  // Priority 5: Too early & Can't verify
  const activeVerdicts = verdicts.filter((v) => getPromiseSortPriority(v.verdict) < 5);
  const bottomVerdicts = verdicts.filter((v) => getPromiseSortPriority(v.verdict) === 5);

  // Sort active verdicts by priority 1 -> 2 -> 3 -> 4
  const sortedActive = [...activeVerdicts].sort((a, b) => {
    const prioA = getPromiseSortPriority(a.verdict);
    const prioB = getPromiseSortPriority(b.verdict);
    if (prioA !== prioB) return prioA - prioB;
    return a.id.localeCompare(b.id, undefined, { numeric: true });
  });

  const renderPromiseRow = (v: PromiseVerdict) => {
    const isExpanded = !!expandedIds[v.id];
    const chip = formatVerdictChip(v.verdict);
    const src = sourcesById[v.id];

    // Document URL for transcript quote
    const docUrl = findDocumentUrl(src?.period || v.made_in, "transcript", meta?.documents_used || []);
    const sourcePdfLink = docUrl ? `${docUrl}#page=${src?.page || 1}` : undefined;

    // Revision label
    const hasRevision = v.revision_label && v.revision_label.toLowerCase() !== "none";

    // Numeric evidence source text (if applicable)
    const hasNumericRef = (v.evidence_ids && v.evidence_ids.length > 0) || v.evidence.match(/N\d+|₹|\d+%/);
    const numericSourceText = hasNumericRef
      ? `Quarterly results${v.applies_to ? `, ${v.applies_to}` : ""} · screener`
      : null;

    // Limit promise statement display words
    const words = v.promise.split(/\s+/);
    const shortPromise = words.length > 18 ? words.slice(0, 16).join(" ") + "…" : v.promise;

    return (
      <article
        key={v.id}
        id={v.id}
        onClick={() => toggleExpand(v.id)}
        className={`group border transition-all cursor-pointer select-none rounded ${
          isExpanded
            ? "border-neutral-400 dark:border-neutral-600 bg-white dark:bg-neutral-900/90 shadow-xs"
            : "border-neutral-200 dark:border-neutral-800/80 bg-neutral-50/40 dark:bg-neutral-900/30 hover:border-neutral-300 dark:hover:border-neutral-700"
        } p-3 space-y-1.5`}
      >
        {/* Header line: Promise, 'said in ...', verdict chip */}
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-0.5 min-w-0 flex-1">
            <div className="flex items-baseline gap-1.5 flex-wrap">
              <span className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                said in {v.made_in || src?.period || "earlier call"}
              </span>
              {hasRevision && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
                  {v.revision_label}
                </span>
              )}
            </div>
            <h3 className="text-sm font-medium text-neutral-950 dark:text-neutral-50 leading-snug">
              {shortPromise}
            </h3>
          </div>

          {/* Verdict chip */}
          <div className="shrink-0 flex items-center gap-1">
            <span
              className={`text-[11px] font-mono px-2 py-0.5 rounded border uppercase tracking-wider font-semibold ${chip.colorClass}`}
            >
              {chip.label}
            </span>
            <span className="text-xs text-neutral-400 dark:text-neutral-500 transition-transform duration-200">
              {isExpanded ? "▴" : "▾"}
            </span>
          </div>
        </div>

        {/* Evidence line */}
        <div className="text-xs text-neutral-600 dark:text-neutral-400 font-mono leading-relaxed pt-0.5">
          <span className="text-neutral-400 dark:text-neutral-500 select-none mr-1.5">↳</span>
          {cleanEvidenceText(v.evidence)}
        </div>

        {/* Expanded View */}
        {isExpanded && (
          <div
            onClick={(e) => e.stopPropagation()}
            className="mt-2.5 pt-2.5 border-t border-neutral-100 dark:border-neutral-800/80 space-y-2 cursor-auto"
          >
            {/* Verbatim quote */}
            {src?.quote ? (
              <blockquote className="border-l-2 border-neutral-300 dark:border-neutral-700 pl-3 py-1 text-[13px] font-serif italic text-neutral-800 dark:text-neutral-200 leading-relaxed bg-neutral-100/40 dark:bg-neutral-800/20 rounded-r">
                “{src.quote}”
              </blockquote>
            ) : (
              <blockquote className="border-l-2 border-neutral-300 dark:border-neutral-700 pl-3 py-1 text-[13px] font-serif italic text-neutral-800 dark:text-neutral-200 leading-relaxed bg-neutral-100/40 dark:bg-neutral-800/20 rounded-r">
                “{v.promise}”
              </blockquote>
            )}

            {/* Speaker & Source Document Link */}
            <div className="flex items-center justify-between gap-2 flex-wrap text-[11px] font-mono text-neutral-500 dark:text-neutral-400">
              <div>
                {src?.speaker ? (
                  <span>
                    <span className="text-neutral-400 dark:text-neutral-500">Speaker: </span>
                    <strong className="font-semibold text-neutral-700 dark:text-neutral-300">
                      {src.speaker}
                    </strong>
                  </span>
                ) : (
                  <span>Management representation</span>
                )}
              </div>

              {sourcePdfLink ? (
                <a
                  href={sourcePdfLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-neutral-700 dark:text-neutral-300 hover:text-black dark:hover:text-white underline decoration-neutral-300 dark:decoration-neutral-700"
                >
                  <span>
                    {src?.period || v.made_in || "Call"} call, p.{src?.page || 1}
                  </span>
                  <span className="text-[10px]">↗</span>
                </a>
              ) : (
                <span>{src?.period || v.made_in || "Earnings call"}</span>
              )}
            </div>

            {/* Numeric evidence source citation */}
            {numericSourceText && (
              <div className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 pt-0.5">
                Numeric evidence: {numericSourceText}
              </div>
            )}
          </div>
        )}
      </article>
    );
  };

  return (
    <section aria-labelledby="promise-list-heading" className="space-y-2.5 pt-2">
      <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
        <h2
          id="promise-list-heading"
          className="text-xs font-mono font-bold uppercase tracking-wider text-neutral-700 dark:text-neutral-300"
        >
          Promises & Guidance ({verdicts.length})
        </h2>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          Ordered by priority
        </span>
      </div>

      {/* Main active promises */}
      <div className="space-y-2">
        {sortedActive.map((v) => renderPromiseRow(v))}
      </div>

      {/* Bottom collapsed group for Too Early & Can't Verify */}
      {bottomVerdicts.length > 0 && (
        <div className="pt-1">
          <button
            type="button"
            onClick={() => setShowBottomGroup(!showBottomGroup)}
            className="w-full py-2 px-3 flex items-center justify-between text-xs font-mono rounded border border-neutral-200 dark:border-neutral-800 bg-neutral-100/50 dark:bg-neutral-900/40 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200 transition-colors"
          >
            <span>
              {bottomVerdicts.length} more: too early or can&apos;t verify
            </span>
            <span className="text-neutral-400">
              {showBottomGroup ? "▴ Hide" : "▾ Show"}
            </span>
          </button>

          {showBottomGroup && (
            <div className="space-y-2 pt-2">
              {bottomVerdicts.map((v) => renderPromiseRow(v))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

