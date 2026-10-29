import Link from "next/link";
import { Company } from "@/lib/types";

interface NoResearchStateProps {
  ticker: string;
  company?: Company | null;
}

export function NoResearchState({ ticker, company }: NoResearchStateProps) {
  const companyName = company?.name;

  return (
    <div className="space-y-4 py-8 text-center max-w-sm mx-auto">
      <div className="flex justify-start mb-4">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-wider text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100 transition-colors"
        >
          <span>←</span>
          <span>FINN Brief</span>
        </Link>
      </div>

      <div className="p-6 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/80 space-y-4">
        <div className="space-y-1">
          <div className="text-xl font-mono font-bold text-neutral-950 dark:text-neutral-50">
            {ticker}
          </div>
          {companyName && (
            <div className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
              {companyName}
            </div>
          )}
          {company?.sector && (
            <div className="text-xs font-mono text-neutral-400 dark:text-neutral-500">
              {company.sector}
            </div>
          )}
        </div>

        <p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed font-sans">
          Primary research has not been compiled for this company yet. Concall transcripts, annual reports, and guidance evaluations are pending.
        </p>

        <div className="pt-2">
          <button
            type="button"
            disabled
            className="w-full py-2 px-4 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-neutral-200 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500 cursor-not-allowed border border-neutral-300 dark:border-neutral-700"
            title="Automated on-demand research will be wired in v5.2"
          >
            Research this company
          </button>
          <span className="block text-[10px] font-mono text-neutral-400 dark:text-neutral-500 mt-1.5">
            On-demand pipeline triggers in v5.2
          </span>
        </div>
      </div>
    </div>
  );
}
