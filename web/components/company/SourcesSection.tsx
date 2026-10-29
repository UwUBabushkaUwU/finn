"use client";

import { useState } from "react";
import { MetaSection } from "@/lib/company";

interface SourcesSectionProps {
  meta?: MetaSection | null;
}

export function SourcesSection({ meta }: SourcesSectionProps) {
  const [isOpen, setIsOpen] = useState(false);
  const docs = meta?.documents_used || [];

  const formatKind = (kind: string) => {
    if (kind === "annual_report") return "Annual Report";
    if (kind === "transcript") return "Earnings Transcript";
    if (kind === "presentation") return "Presentation";
    return kind;
  };

  return (
    <section aria-labelledby="sources-heading" className="space-y-2 pt-2 border-t border-neutral-200 dark:border-neutral-800">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full py-2 px-3 flex items-center justify-between text-xs font-mono rounded border border-neutral-200 dark:border-neutral-800 bg-neutral-50/50 dark:bg-neutral-900/40 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200 transition-colors"
      >
        <span id="sources-heading" className="font-semibold">
          Sources ({docs.length} primary documents)
        </span>
        <span className="text-neutral-400">
          {isOpen ? "▴ Collapse" : "▾ Expand"}
        </span>
      </button>

      {isOpen && (
        <div className="p-3 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/90 space-y-2 text-xs font-mono">
          <div className="space-y-1.5 divide-y divide-neutral-100 dark:divide-neutral-800/80">
            {docs.map((doc, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between gap-2 pt-1.5 first:pt-0"
              >
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <span className="text-[10px] uppercase px-1.5 py-0.2 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 shrink-0">
                    {formatKind(doc.kind)}
                  </span>
                  <span className="font-semibold text-neutral-800 dark:text-neutral-200 truncate">
                    {doc.period || "Document"}
                  </span>
                </div>

                <a
                  href={doc.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100 underline decoration-neutral-300 dark:decoration-neutral-700 shrink-0 flex items-center gap-0.5"
                >
                  <span>PDF</span>
                  <span className="text-[10px]">↗</span>
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* FINN primary source charter note */}
      <p className="text-[11px] font-serif italic text-neutral-500 dark:text-neutral-400 leading-snug px-1">
        FINN uses only company documents: earnings-call transcripts, presentations, the annual report and reported financials. No news or broker research.
      </p>
    </section>
  );
}
