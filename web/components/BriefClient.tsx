"use client";

import { useState, useMemo } from "react";
import { Company, Filing, Alert, Price, GroupedEvent } from "@/lib/types";
import { groupFilingsIntoEvents } from "@/lib/grouping";
import { Header } from "./Header";
import { TimeChips, TimeWindowKey } from "./TimeChips";
import { AlertsStrip } from "./AlertsStrip";
import { EventCard } from "./EventCard";
import { RoutineSection } from "./RoutineSection";
import { EmptyState } from "./EmptyState";

interface BriefClientProps {
  initialWindow: TimeWindowKey;
  todayFormatted: string;
  filings: Filing[];
  companiesMap: Record<string, Company>;
  alerts: Alert[];
  pricesMap: Record<string, Price>;
}

const HOURS_MAP: Record<TimeWindowKey, number> = {
  "24h": 24,
  "3d": 72,
  "7d": 168,
  "30d": 720,
};

const WINDOW_LABEL_MAP: Record<TimeWindowKey, string> = {
  "24h": "last 24 hours",
  "3d": "last 3 days",
  "7d": "last 7 days",
  "30d": "last 30 days",
};

export function BriefClient({
  initialWindow,
  todayFormatted,
  filings,
  companiesMap,
  alerts,
  pricesMap,
}: BriefClientProps) {
  const [activeWindow, setActiveWindow] = useState<TimeWindowKey>(initialWindow);

  const handleWindowChange = (w: TimeWindowKey) => {
    setActiveWindow(w);
    const newUrl = w === "24h" ? "/" : `/?w=${w}`;
    window.history.replaceState(null, "", newUrl);
  };

  const windowLabel = WINDOW_LABEL_MAP[activeWindow];

  // In-memory filter on phone: 0ms latency, no server request
  const filteredFilings = useMemo(() => {
    const hours = HOURS_MAP[activeWindow];
    const cutoffMs = Date.now() - hours * 60 * 60 * 1000;
    return filings.filter((f) => new Date(f.filed_at).getTime() >= cutoffMs);
  }, [filings, activeWindow]);

  // Group filtered filings into events
  const events: GroupedEvent[] = useMemo(() => {
    return groupFilingsIntoEvents(filteredFilings, companiesMap);
  }, [filteredFilings, companiesMap]);

  // Partition events by priority
  const needsAttention = useMemo(() => events.filter((e) => e.priority === 1), [events]);
  const worthKnowing = useMemo(() => events.filter((e) => e.priority === 2), [events]);
  const routine = useMemo(() => events.filter((e) => e.priority === 3), [events]);

  const routineFilingsCount = useMemo(
    () => routine.reduce((acc, ev) => acc + 1 + ev.secondaryFilings.length, 0),
    [routine]
  );

  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
      <div className="mx-auto max-w-xl px-4 py-4 sm:px-6 space-y-4">
        {/* Header with live reactive counts */}
        <Header
          todayDate={todayFormatted}
          attentionCount={needsAttention.length}
          worthKnowingCount={worthKnowing.length}
          routineCount={routineFilingsCount}
        />

        {/* Instant Time Window Chips */}
        <TimeChips activeWindow={activeWindow} onWindowChange={handleWindowChange} />

        {/* Alerts Strip */}
        <AlertsStrip alerts={alerts} pricesMap={pricesMap} />

        {/* Section 1: Needs Attention (Priority 1) */}
        <section aria-labelledby="needs-attention-heading" className="space-y-2 pt-1">
          <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
            <h2
              id="needs-attention-heading"
              className="text-xs font-mono font-bold uppercase tracking-wider text-amber-700 dark:text-amber-500"
            >
              Needs Attention ({needsAttention.length})
            </h2>
            <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
              Priority 1 · {activeWindow}
            </span>
          </div>

          {needsAttention.length > 0 ? (
            <div className="space-y-2">
              {needsAttention.map((event) => (
                <EventCard key={event.id} event={event} isCompact={false} />
              ))}
            </div>
          ) : (
            <EmptyState
              message={`Nothing needs your attention in the ${windowLabel}.`}
              suggest7d={activeWindow === "24h"}
              onSelect7d={() => handleWindowChange("7d")}
            />
          )}
        </section>

        {/* Section 2: Worth Knowing (Priority 2) */}
        <section aria-labelledby="worth-knowing-heading" className="space-y-2 pt-2">
          <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
            <h2
              id="worth-knowing-heading"
              className="text-xs font-mono font-bold uppercase tracking-wider text-neutral-600 dark:text-neutral-400"
            >
              Worth Knowing ({worthKnowing.length})
            </h2>
            <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
              Priority 2 · {activeWindow}
            </span>
          </div>

          {worthKnowing.length > 0 ? (
            <div className="space-y-1.5">
              {worthKnowing.map((event) => (
                <EventCard key={event.id} event={event} isCompact={true} />
              ))}
            </div>
          ) : (
            <EmptyState
              message={`No secondary filings in the ${windowLabel}.`}
              suggest7d={activeWindow === "24h" && needsAttention.length === 0}
              onSelect7d={() => handleWindowChange("7d")}
            />
          )}
        </section>

        {/* Section 3: Routine (Priority 3) */}
        <RoutineSection routineEvents={routine} />

        {/* Footer */}
        <footer className="pt-6 pb-4 border-t border-neutral-200 dark:border-neutral-800 text-center">
          <p className="text-[10px] font-mono text-neutral-400 dark:text-neutral-600">
            FINN · Primary Exchange Filings & Portfolio Alerts · IST
          </p>
        </footer>
      </div>
    </main>
  );
}

