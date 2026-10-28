"use client";

import { useState } from "react";
import { GroupedEvent } from "@/lib/types";
import { formatFilingTime } from "@/lib/time";
import { formatCategory } from "@/lib/grouping";
import { ResultsBlock } from "./ResultsBlock";
import { PeopleBlock } from "./PeopleBlock";

interface EventCardProps {
  event: GroupedEvent;
  isCompact?: boolean; // True for Worth Knowing (Priority 2)
}

export function EventCard({ event, isCompact = false }: EventCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isPriority1 = event.priority === 1;
  const hasSecondary = event.secondaryFilings.length > 0;

  // Determine if results block should have "Also: Q2 results" prefix
  const isSecondaryResults =
    Boolean(event.resultsEnrichment) &&
    event.category.toLowerCase() !== "results";

  // Noise filter for Details box
  const hasValidDescription =
    Boolean(event.primaryFiling.description) &&
    !event.primaryFiling.description?.includes("has informed the Exchange") &&
    event.primaryFiling.description !== event.headline;

  return (
    <article
      onClick={() => setExpanded(!expanded)}
      className={`group cursor-pointer transition-colors border select-none ${
        isPriority1
          ? "border-neutral-300 dark:border-neutral-700/80 bg-white dark:bg-neutral-900/90 border-l-[3px] border-l-amber-600 dark:border-l-amber-500"
          : "border-neutral-200 dark:border-neutral-800/80 bg-neutral-50/40 dark:bg-neutral-900/40 hover:bg-white dark:hover:bg-neutral-900"
      } ${isCompact ? "p-2.5" : "p-3"}`}
    >
      {/* Header row: Ticker, Company, Category Chips, Time */}
      <div className="flex items-center gap-2 justify-between">
        <div className="flex items-baseline gap-1.5 min-w-0">
          <span className="font-mono font-bold text-sm tracking-tight text-neutral-950 dark:text-neutral-50">
            {event.ticker}
          </span>
          <span className="text-xs text-neutral-500 dark:text-neutral-400 truncate max-w-[120px] sm:max-w-[200px]">
            {event.companyName}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
          {(event.categories && event.categories.length > 0
            ? event.categories
            : [event.category]
          ).map((cat) => (
            <span
              key={cat}
              className="inline-block text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.2 rounded border border-neutral-200 dark:border-neutral-700/80 text-neutral-600 dark:text-neutral-300 bg-neutral-100/50 dark:bg-neutral-800/50"
            >
              {cat}
            </span>
          ))}
          <time className="text-[11px] font-mono tabular-nums text-neutral-500 dark:text-neutral-400">
            {formatFilingTime(event.filedAt)}
          </time>
        </div>
      </div>

      {/* Main Headline */}
      <p
        className={`mt-1.5 leading-snug ${
          isPriority1
            ? "text-[13px] font-medium text-neutral-900 dark:text-neutral-100"
            : "text-xs text-neutral-800 dark:text-neutral-200"
        }`}
      >
        {event.headline}
      </p>

      {/* Results Block (if event has results enrichment) */}
      {event.resultsEnrichment && (
        <ResultsBlock
          results={event.resultsEnrichment}
          isAlso={isSecondaryResults}
        />
      )}

      {/* People Block (if event has people enrichment) */}
      {event.peopleEnrichment && event.peopleEnrichment.length > 0 && (
        <PeopleBlock
          people={event.peopleEnrichment}
          companyName={event.companyName}
        />
      )}

      {/* Footer row: +N more badge & PDF link */}
      <div className="mt-2.5 flex items-center justify-between text-xs pt-1.5 border-t border-neutral-150 dark:border-neutral-850">
        <div className="flex items-center gap-2">
          {hasSecondary && (
            <span
              className={`text-[11px] font-mono font-medium px-1.5 py-0.5 rounded ${
                expanded
                  ? "bg-neutral-200 text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100"
                  : "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300 group-hover:bg-neutral-200 dark:group-hover:bg-neutral-700"
              }`}
            >
              {expanded ? "Hide related" : `+${event.secondaryFilings.length} more`}
            </span>
          )}
        </div>

        {event.attachmentUrl && (
          <a
            href={event.attachmentUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="font-mono text-[11px] font-semibold text-neutral-700 dark:text-neutral-300 hover:text-neutral-950 dark:hover:text-neutral-50 underline decoration-neutral-300 dark:decoration-neutral-600 underline-offset-2 px-1"
          >
            PDF ↗
          </a>
        )}
      </div>

      {/* Expanded cluster details */}
      {expanded && (
        <div
          className="mt-3 pt-2.5 border-t border-neutral-200 dark:border-neutral-800 space-y-2 text-xs"
          onClick={(e) => e.stopPropagation()}
        >
          {hasValidDescription && (
            <div className="text-[11px] text-neutral-600 dark:text-neutral-400 bg-neutral-100/60 dark:bg-neutral-800/60 p-2 rounded">
              <span className="font-mono font-semibold uppercase text-[10px] text-neutral-400 dark:text-neutral-500 block mb-0.5">
                Details
              </span>
              {event.primaryFiling.description}
            </div>
          )}

          {hasSecondary && (
            <div className="space-y-1.5 pt-1">
              <span className="font-mono text-[10px] uppercase font-bold tracking-wider text-neutral-400 dark:text-neutral-500 block">
                Related filings in this event ({event.secondaryFilings.length})
              </span>
              <ul className="space-y-1.5">
                {event.secondaryFilings.map((sf) => (
                  <li
                    key={sf.id}
                    className="flex items-start justify-between gap-2 p-1.5 rounded bg-neutral-100/40 dark:bg-neutral-800/40 border border-neutral-200/50 dark:border-neutral-800/50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className="text-[9px] font-mono uppercase px-1 py-0.2 rounded border border-neutral-200 dark:border-neutral-700 text-neutral-500 dark:text-neutral-400">
                          {formatCategory(sf.category)}
                        </span>
                        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 tabular-nums">
                          {formatFilingTime(sf.filed_at)}
                        </span>
                      </div>
                      <p className="text-[11px] text-neutral-800 dark:text-neutral-200 leading-tight">
                        {sf.summary?.trim() || sf.subject}
                      </p>
                    </div>

                    {sf.attachment_url && (
                      <a
                        href={sf.attachment_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-[10px] font-semibold text-neutral-700 dark:text-neutral-300 hover:text-neutral-950 dark:hover:text-neutral-50 underline decoration-neutral-300 dark:decoration-neutral-600 shrink-0 self-center"
                      >
                        PDF ↗
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
