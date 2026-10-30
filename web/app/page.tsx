import { Metadata } from "next";
import { supabase } from "@/lib/supabase";
import { Company, Filing, Alert, Price } from "@/lib/types";
import { parseTimeWindow, getTodayFormattedIST } from "@/lib/time";
import { BriefClient } from "@/components/BriefClient";
import { TimeWindowKey } from "@/components/TimeChips";

export const metadata: Metadata = {
  title: "Brief",
};

export const revalidate = 60;

interface PageProps {
  searchParams: Promise<{ w?: string }>;
}

export default async function BriefPage({ searchParams }: PageProps) {
  const { w } = await searchParams;
  const { window: activeWindow } = parseTimeWindow(w);

  // Reference now in UTC, fetch last 30 days once for instant client-side switching
  const now = new Date();
  const cutoffDate30d = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString();

  // Run all queries in parallel, selecting strictly the columns needed and never fetching raw
  const [companiesRes, filingsRes, alertsRes, pricesRes] = await Promise.all([
    supabase
      .from("companies")
      .select("ticker, name, in_portfolio")
      .eq("in_portfolio", true),

    supabase
      .from("filings")
      .select(
        "id, ticker, exchange, filed_at, subject, description, attachment_url, category, priority, summary, enrichment, companies!inner(in_portfolio)"
      )
      .eq("companies.in_portfolio", true)
      .gte("filed_at", cutoffDate30d)
      .order("filed_at", { ascending: false }),

    supabase
      .from("alerts")
      .select(
        "id, ticker, kind, message, value, trigger_date, seen, companies!inner(in_portfolio)"
      )
      .eq("companies.in_portfolio", true)
      .in("kind", ["volume_spike", "price_move"])
      .order("trigger_date", { ascending: false })
      .limit(20),

    supabase
      .from("prices")
      .select("ticker, date, close, pct_change, vol_ratio, companies!inner(in_portfolio)")
      .eq("companies.in_portfolio", true)
      .order("date", { ascending: false })
      .limit(100),
  ]);

  // Build companies lookup map
  const companiesMap: Record<string, Company> = {};
  for (const c of companiesRes.data || []) {
    companiesMap[c.ticker] = c as Company;
  }

  // Trim description to prevent heavy strings, discard inner join metadata
  const filings: Filing[] = (filingsRes.data || []).map((f) => ({
    id: f.id,
    ticker: f.ticker,
    exchange: f.exchange,
    filed_at: f.filed_at,
    subject: f.subject,
    description: f.description
      ? f.description.length > 300
        ? f.description.slice(0, 300) + "…"
        : f.description
      : null,
    attachment_url: f.attachment_url,
    category: f.category,
    priority: f.priority,
    summary: f.summary,
    enrichment: f.enrichment,
  }));

  // Build latest prices lookup map
  const pricesMap: Record<string, Price> = {};
  for (const p of pricesRes.data || []) {
    if (!pricesMap[p.ticker]) {
      pricesMap[p.ticker] = p as Price;
    }
  }

  // Extract alerts for the latest active trading day
  const rawAlerts = alertsRes.data || [];
  let alerts: Alert[] = [];
  if (rawAlerts.length > 0) {
    const latestDate = rawAlerts[0].trigger_date;
    alerts = rawAlerts
      .filter((a) => a.trigger_date === latestDate)
      .map((a) => ({
        id: a.id,
        ticker: a.ticker,
        kind: a.kind as Alert["kind"],
        message: a.message || "",
        value: a.value,
        trigger_date: a.trigger_date,
        seen: a.seen || false,
      }));
  }

  const todayFormatted = getTodayFormattedIST(now);

  return (
    <BriefClient
      initialWindow={activeWindow as TimeWindowKey}
      todayFormatted={todayFormatted}
      filings={filings}
      companiesMap={companiesMap}
      alerts={alerts}
      pricesMap={pricesMap}
    />
  );
}
