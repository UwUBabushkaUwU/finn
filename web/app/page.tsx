import { Metadata } from "next";
import { supabase } from "@/lib/supabase";
import { Company, Filing, Alert, Price } from "@/lib/types";
import { parseTimeWindow, getTodayFormattedIST } from "@/lib/time";
import { groupFilingsIntoEvents } from "@/lib/grouping";
import { Header } from "@/components/Header";
import { TimeChips } from "@/components/TimeChips";
import { AlertsStrip } from "@/components/AlertsStrip";
import { EventCard } from "@/components/EventCard";
import { RoutineSection } from "@/components/RoutineSection";
import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = {
  title: "Brief",
};

export const revalidate = 60;

interface PageProps {
  searchParams: Promise<{ w?: string }>;
}

export default async function BriefPage({ searchParams }: PageProps) {
  const { w } = await searchParams;
  const { window: activeWindow, hours, label: windowLabel } = parseTimeWindow(w);

  // Reference now in UTC
  const now = new Date();
  const cutoffDate = new Date(now.getTime() - hours * 60 * 60 * 1000).toISOString();

  // 1. Fetch portfolio companies
  const { data: rawCompanies } = await supabase
    .from("companies")
    .select("*")
    .eq("in_portfolio", true);

  const companies: Company[] = (rawCompanies || []) as Company[];
  const portfolioTickers = companies.map((c) => c.ticker);
  const companiesMap: Record<string, Company> = {};
  for (const c of companies) {
    companiesMap[c.ticker] = c;
  }

  // 2. Fetch filings for portfolio companies in the chosen time window
  let filings: Filing[] = [];
  if (portfolioTickers.length > 0) {
    const { data: rawFilings } = await supabase
      .from("filings")
      .select("*")
      .in("ticker", portfolioTickers)
      .gte("filed_at", cutoffDate)
      .order("filed_at", { ascending: false });

    filings = (rawFilings || []) as Filing[];
  }

  // 3. Fetch today's price and volume alerts
  // Trigger date in IST: YYYY-MM-DD
  const todayISTStr = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);

  let alerts: Alert[] = [];
  if (portfolioTickers.length > 0) {
    const { data: rawAlerts } = await supabase
      .from("alerts")
      .select("*")
      .in("ticker", portfolioTickers)
      .in("kind", ["volume_spike", "price_move"])
      .eq("trigger_date", todayISTStr)
      .order("id", { ascending: false });

    alerts = (rawAlerts || []) as Alert[];

    // If no alerts found for today's exact date, check the latest available alert trigger date
    if (alerts.length === 0) {
      const { data: latestAlerts } = await supabase
        .from("alerts")
        .select("*")
        .in("ticker", portfolioTickers)
        .in("kind", ["volume_spike", "price_move"])
        .order("trigger_date", { ascending: false })
        .limit(10);

      if (latestAlerts && latestAlerts.length > 0) {
        const latestDate = latestAlerts[0].trigger_date;
        alerts = latestAlerts.filter((a) => a.trigger_date === latestDate) as Alert[];
      }
    }
  }

  // 4. Fetch latest price rows for portfolio companies to determine direction (▲ / ▼)
  const pricesMap: Record<string, Price> = {};
  if (portfolioTickers.length > 0) {
    const { data: rawPrices } = await supabase
      .from("prices")
      .select("ticker, date, close, pct_change, vol_ratio")
      .in("ticker", portfolioTickers)
      .order("date", { ascending: false })
      .limit(100);

    for (const p of rawPrices || []) {
      if (!pricesMap[p.ticker]) {
        pricesMap[p.ticker] = p as Price;
      }
    }
  }

  // 5. Group filings into events
  const events = groupFilingsIntoEvents(filings, companiesMap);

  // 6. Partition events by priority
  const needsAttention = events.filter((e) => e.priority === 1);
  const worthKnowing = events.filter((e) => e.priority === 2);
  const routine = events.filter((e) => e.priority === 3);

  // Routine total filings count (including grouped ones)
  const routineFilingsCount = routine.reduce(
    (acc, ev) => acc + 1 + ev.secondaryFilings.length,
    0
  );

  const todayFormatted = getTodayFormattedIST(now);

  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
      <div className="mx-auto max-w-xl px-4 py-4 sm:px-6 space-y-4">
        {/* Header */}
        <Header
          todayDate={todayFormatted}
          attentionCount={needsAttention.length}
          worthKnowingCount={worthKnowing.length}
          routineCount={routineFilingsCount}
        />

        {/* Time Window Chips */}
        <TimeChips />

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
