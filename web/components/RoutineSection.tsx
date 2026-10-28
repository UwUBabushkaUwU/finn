"use client";

import { useState } from "react";
import { GroupedEvent } from "@/lib/types";
import { formatFilingTime } from "@/lib/time";

interface RoutineSectionProps {
  routineEvents: GroupedEvent[];
}

export function RoutineSection({ routineEvents }: RoutineSectionProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Total filings count across all routine events
  const totalFilings = routineEvents.reduce(
    (acc, ev) => acc + 1 + ev.secondaryFilings.length,
    0
  );

  if (totalFilings === 0) {
    return null;
  }

  return (
    <section className="pt-2 border-t border-neutral-200 dark:border-neutral-800">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between py-2 text-left text-xs font-mono text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-200 transition-colors"
      >
        <div className="flex items-center gap-1.5 tabular-nums">
          <span className="text-[10px] opacity-70">{isExpanded ? "▾" : "▸"}</span>
          <span>{totalFilings} routine filings</span>
        </div>
        <span className="text-[11px] opacity-60">
          {isExpanded ? "collapse" : "expand"}
        </span>
      </button>

      {isExpanded && (
        <div className="mt-1 divide-y divide-neutral-100 dark:divide-neutral-850 border-t border-neutral-100 dark:border-neutral-850 text-xs font-mono">
          {routineEvents.map((event) => {
            // Flatten all filings in this routine event
            const allFilings = [event.primaryFiling, ...event.secondaryFilings];

            return allFilings.map((filing) => (
              <div
                key={filing.id}
                className="py-1.5 flex items-start justify-between gap-2 hover:bg-neutral-50 dark:hover:bg-neutral-900/50 px-1 rounded transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-bold text-[11px] text-neutral-900 dark:text-neutral-200">
                      {filing.ticker}
                    </span>
                    <span className="text-[10px] text-neutral-400 dark:text-neutral-500 truncate max-w-[120px]">
                      {event.companyName}
                    </span>
                  </div>
                  <p className="text-[11px] text-neutral-600 dark:text-neutral-400 line-clamp-1">
                    {filing.subject}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] tabular-nums text-neutral-400 dark:text-neutral-500">
                    {formatFilingTime(filing.filed_at)}
                  </span>
                  {filing.attachment_url && (
                    <a
                      href={filing.attachment_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] font-semibold text-neutral-700 dark:text-neutral-300 hover:underline"
                    >
                      PDF
                    </a>
                  )}
                </div>
              </div>
            ));
          })}
        </div>
      )}
    </section>
  );
}
