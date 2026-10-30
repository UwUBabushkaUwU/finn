import { Metadata } from "next";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { ResearchSearchInput } from "@/components/ResearchSearchInput";
import { mapVerdictToGroup } from "@/lib/company";

export const metadata: Metadata = {
  title: "Research",
  description: "Primary-source corporate analysis, management promises, and financial reality.",
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface ResearchedCompanyItem {
  ticker: string;
  name: string;
  inPortfolio: boolean;
  keptCount: number;
  brokenCount: number;
  behindCount: number;
  otherProgressCount: number;
  tooEarlyCount: number;
  cantVerifyCount: number;
  totalTargets: number;
  finishedAt?: string | null;
}

export default async function ResearchPage() {
  // Fetch completed jobs, companies, and research sections in parallel
  const [jobsRes, companiesRes, researchRes] = await Promise.all([
    supabase
      .from("research_jobs")
      .select("ticker, status, finished_at")
      .eq("status", "done"),
    supabase.from("companies").select("ticker, name, in_portfolio"),
    supabase
      .from("research")
      .select("ticker, section, content")
      .in("section", ["meta", "promises"]),
  ]);

  const jobs = jobsRes.data || [];
  const completedTickersSet = new Set(jobs.map((j) => j.ticker));

  const companiesByTicker = new Map(
    (companiesRes.data || []).map((c) => [c.ticker, c])
  );

  const researchByTicker = new Map<string, { meta?: any; promises?: any }>();
  for (const r of researchRes.data || []) {
    if (!completedTickersSet.has(r.ticker)) continue;
    const cur = researchByTicker.get(r.ticker) || {};
    if (r.section === "meta") cur.meta = r.content;
    if (r.section === "promises") cur.promises = r.content;
    researchByTicker.set(r.ticker, cur);
  }

  // Assemble and process company items
  const items: ResearchedCompanyItem[] = jobs.map((job) => {
    const ticker = job.ticker;
    const company = companiesByTicker.get(ticker);
    const research = researchByTicker.get(ticker);

    const name = company?.name || research?.meta?.company_name || ticker;
    const inPortfolio = Boolean(company?.in_portfolio);

    let keptCount = 0;
    let brokenCount = 0;
    let behindCount = 0;
    let otherProgressCount = 0;
    let tooEarlyCount = 0;
    let cantVerifyCount = 0;

    const verdicts = research?.promises?.verdicts || [];
    for (const v of verdicts) {
      const group = mapVerdictToGroup(v.verdict);
      const norm = (v.verdict || "").toLowerCase().trim();
      if (group === "kept") keptCount++;
      else if (group === "broken") brokenCount++;
      else if (group === "in_progress") {
        if (norm === "behind") behindCount++;
        else otherProgressCount++;
      } else if (group === "too_early") tooEarlyCount++;
      else cantVerifyCount++;
    }

    return {
      ticker,
      name,
      inPortfolio,
      keptCount,
      brokenCount,
      behindCount,
      otherProgressCount,
      tooEarlyCount,
      cantVerifyCount,
      totalTargets: verdicts.length,
      finishedAt: job.finished_at,
    };
  });

  // Sort: Portfolio companies first, then others alphabetically
  items.sort((a, b) => {
    if (a.inPortfolio && !b.inPortfolio) return -1;
    if (!a.inPortfolio && b.inPortfolio) return 1;
    return a.ticker.localeCompare(b.ticker);
  });

  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
      <div className="mx-auto max-w-xl px-4 py-6 sm:px-6 space-y-6">
        {/* Page Header */}
        <header className="border-b border-neutral-200 dark:border-neutral-800 pb-4">
          <div className="flex items-baseline justify-between mb-1">
            <h1 className="font-serif text-2xl font-normal tracking-tight text-neutral-950 dark:text-neutral-50">
              Research
            </h1>
            <span className="text-[11px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
              {items.length} Researched
            </span>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 font-sans">
            Primary-source analysis, guidance tracking, and audited financials on NSE companies.
          </p>
        </header>

        {/* Search & Action Input */}
        <section aria-label="Search ticker">
          <ResearchSearchInput />
        </section>

        {/* Researched Companies List */}
        <section className="space-y-3 pt-2">
          <div className="flex items-center justify-between border-b border-neutral-200/80 dark:border-neutral-800/80 pb-1.5">
            <h2 className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
              Researched Companies
            </h2>
            <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
              Tap to view
            </span>
          </div>

          {items.length === 0 ? (
            <div className="rounded border border-dashed border-neutral-200 dark:border-neutral-800 p-8 text-center text-xs text-neutral-400">
              No companies researched yet. Type a ticker above to run research.
            </div>
          ) : (
            <div className="divide-y divide-neutral-100 dark:divide-neutral-900 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 overflow-hidden">
              {items.map((company) => {
                const total = company.totalTargets;
                const keptPct = total > 0 ? (company.keptCount / total) * 100 : 0;
                const brokenPct = total > 0 ? (company.brokenCount / total) * 100 : 0;
                const behindPct = total > 0 ? (company.behindCount / total) * 100 : 0;
                const otherPct = total > 0 ? (company.otherProgressCount / total) * 100 : 0;
                const tooEarlyPct = total > 0 ? (company.tooEarlyCount / total) * 100 : 0;
                const cantVerifyPct = total > 0 ? (company.cantVerifyCount / total) * 100 : 0;

                let summaryText = `${company.keptCount} kept · ${company.brokenCount} broken`;
                if (company.keptCount === 0 && company.brokenCount === 0) {
                  const parts: string[] = [];
                  if (company.tooEarlyCount > 0) parts.push(`${company.tooEarlyCount} too early`);
                  if (company.otherProgressCount > 0) parts.push(`${company.otherProgressCount} on track`);
                  if (company.behindCount > 0) parts.push(`${company.behindCount} behind`);
                  if (company.cantVerifyCount > 0) parts.push(`${company.cantVerifyCount} can't verify`);
                  if (parts.length > 0) {
                    summaryText = parts.join(" · ");
                  }
                }

                return (
                  <Link
                    key={company.ticker}
                    href={`/c/${company.ticker}`}
                    className="block p-3.5 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors group"
                  >
                    <div className="flex items-baseline justify-between mb-1.5">
                      <div className="flex items-baseline gap-2">
                        <span className="font-mono text-sm font-bold tracking-tight text-neutral-950 dark:text-neutral-50 group-hover:underline">
                          {company.ticker}
                        </span>
                        <span className="text-xs font-sans text-neutral-600 dark:text-neutral-400 truncate max-w-[200px]">
                          {company.name}
                        </span>
                      </div>
                      {company.inPortfolio && (
                        <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700">
                          Portfolio
                        </span>
                      )}
                    </div>

                    {/* Tiny segmented bar + summary text */}
                    <div className="flex items-center gap-3">
                      {total > 0 ? (
                        <div
                          aria-hidden="true"
                          className="h-1.5 w-24 rounded-full overflow-hidden flex bg-neutral-100 dark:bg-neutral-800 shrink-0"
                        >
                          {keptPct > 0 && (
                            <div
                              style={{ width: `${keptPct}%` }}
                              className="h-full bg-emerald-600 dark:bg-emerald-500"
                            />
                          )}
                          {brokenPct > 0 && (
                            <div
                              style={{ width: `${brokenPct}%` }}
                              className="h-full bg-rose-600 dark:bg-rose-500"
                            />
                          )}
                          {behindPct > 0 && (
                            <div
                              style={{ width: `${behindPct}%` }}
                              className="h-full bg-amber-500 dark:bg-amber-400"
                            />
                          )}
                          {otherPct > 0 && (
                            <div
                              style={{ width: `${otherPct}%` }}
                              className="h-full bg-neutral-400 dark:bg-neutral-600"
                            />
                          )}
                          {tooEarlyPct > 0 && (
                            <div
                              style={{ width: `${tooEarlyPct}%` }}
                              className="h-full bg-neutral-300 dark:bg-neutral-700"
                            />
                          )}
                          {cantVerifyPct > 0 && (
                            <div
                              style={{ width: `${cantVerifyPct}%` }}
                              className="h-full bg-neutral-200 dark:bg-neutral-800"
                            />
                          )}
                        </div>
                      ) : (
                        <div className="h-1.5 w-24 rounded-full bg-neutral-200 dark:bg-neutral-800 shrink-0" />
                      )}

                      <span className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400">
                        {summaryText}
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
