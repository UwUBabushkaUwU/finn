import { Metadata } from "next";
import { supabase } from "@/lib/supabase";
import { Company, Price } from "@/lib/types";
import {
  MetaSection,
  PromisesSection,
  PromiseSourceItem,
  GuidanceTimelineSection,
  NumbersSection as NumbersData,
  SnapshotSection,
  BullBearSection as BullBearData,
  FinancialsRow,
} from "@/lib/company";
import { CompanyHeader } from "@/components/company/CompanyHeader";
import { ManagementHero } from "@/components/company/ManagementHero";
import { PromiseList } from "@/components/company/PromiseList";
import { StoryChanged } from "@/components/company/StoryChanged";
import { NumbersSection } from "@/components/company/NumbersSection";
import { BusinessSnapshot } from "@/components/company/BusinessSnapshot";
import { BullBearSection } from "@/components/company/BullBearSection";
import { SourcesSection } from "@/components/company/SourcesSection";
import { NoResearchState } from "@/components/company/NoResearchState";
import { ResearchProgress, ResearchJob } from "@/components/company/ResearchProgress";

export const revalidate = 300;

interface PageProps {
  params: Promise<{ ticker: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { ticker: rawTicker } = await params;
  const ticker = decodeURIComponent(rawTicker).toUpperCase();
  return {
    title: `${ticker} — Primary Research · FINN`,
    description: `Primary-source research, guidance tracking, and financial reality for ${ticker}.`,
  };
}

export default async function CompanyPage({ params }: PageProps) {
  const { ticker: rawTicker } = await params;
  const ticker = decodeURIComponent(rawTicker).toUpperCase();

  // Run queries in parallel
  const [researchRes, priceRes, financialsRes, companyRes, jobRes] = await Promise.all([
    supabase.from("research").select("*").eq("ticker", ticker),
    supabase
      .from("prices")
      .select("*")
      .eq("ticker", ticker)
      .order("date", { ascending: false })
      .limit(1),
    supabase.from("financials").select("*").eq("ticker", ticker).maybeSingle(),
    supabase.from("companies").select("*").eq("ticker", ticker).maybeSingle(),
    supabase.from("research_jobs").select("*").eq("ticker", ticker).maybeSingle(),
  ]);

  const researchRows = researchRes.data || [];
  const latestPrice = (priceRes.data?.[0] as Price) || null;
  const financials = (financialsRes.data as FinancialsRow) || null;
  const company = (companyRes.data as Company) || null;
  const job = (jobRes.data as ResearchJob) || null;

  // If a job is actively queued, running, or failed, render the progress / error screen
  if (job && (job.status === "queued" || job.status === "running" || job.status === "failed")) {
    return (
      <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
        <div className="mx-auto max-w-xl px-4 py-4 sm:px-6">
          <ResearchProgress ticker={ticker} initialJob={job} company={company} />
        </div>
      </main>
    );
  }

  // If no research rows exist for this ticker, render the calm empty state
  if (researchRows.length === 0) {
    return (
      <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
        <div className="mx-auto max-w-xl px-4 py-4 sm:px-6">
          <NoResearchState ticker={ticker} company={company} />
        </div>
      </main>
    );
  }

  // Parse out sections from research rows
  let meta: MetaSection | null = null;
  let promises: PromisesSection | null = null;
  let promiseSources: PromiseSourceItem[] = [];
  let guidanceTimeline: GuidanceTimelineSection | null = null;
  let numbers: NumbersData | null = null;
  let snapshot: SnapshotSection | null = null;
  let bullBear: BullBearData | null = null;

  for (const row of researchRows) {
    if (row.section === "meta") {
      meta = row.content as MetaSection;
    } else if (row.section === "promises") {
      promises = row.content as PromisesSection;
      if (Array.isArray(row.sources)) {
        promiseSources = row.sources as PromiseSourceItem[];
      }
    } else if (row.section === "guidance_timeline") {
      guidanceTimeline = row.content as GuidanceTimelineSection;
    } else if (row.section === "numbers") {
      numbers = row.content as NumbersData;
    } else if (row.section === "snapshot") {
      snapshot = row.content as SnapshotSection;
    } else if (row.section === "bull_bear") {
      bullBear = row.content as BullBearData;
    }
  }

  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800">
      <div className="mx-auto max-w-xl px-4 py-4 sm:px-6 space-y-4">
        {/* Header */}
        <CompanyHeader
          ticker={ticker}
          company={company}
          meta={meta}
          price={latestPrice}
        />

        {/* Hero: "Did management deliver?" */}
        <ManagementHero promises={promises} />

        {/* The Promise List */}
        <PromiseList
          verdicts={promises?.verdicts || []}
          sources={promiseSources}
          meta={meta}
        />

        {/* How the story changed (Guidance timeline revisions) */}
        <StoryChanged guidanceTimeline={guidanceTimeline} />

        {/* The Numbers: 4 tiles, SVG chart, flags */}
        <NumbersSection numbers={numbers} financials={financials} />

        {/* What the business is (Snapshot) */}
        <BusinessSnapshot snapshot={snapshot} meta={meta} />

        {/* Bull vs Bear Case */}
        <BullBearSection
          bullBear={bullBear}
          promises={promises}
          numbers={numbers}
          snapshot={snapshot}
        />

        {/* Sources disclosure & FINN methodology notice */}
        <SourcesSection meta={meta} />

        {/* Quiet Page Footer */}
        <footer className="pt-4 pb-6 border-t border-neutral-200 dark:border-neutral-800 text-center">
          <p className="text-[10px] font-mono text-neutral-400 dark:text-neutral-600">
            FINN Primary Research · Primary Transcripts & Financials
          </p>
        </footer>
      </div>
    </main>
  );
}

