"use client";

import {
  BullBearSection as BullBearData,
  PromisesSection,
  NumbersSection,
  SnapshotSection,
} from "@/lib/company";

interface BullBearSectionProps {
  bullBear?: BullBearData | null;
  promises?: PromisesSection | null;
  numbers?: NumbersSection | null;
  snapshot?: SnapshotSection | null;
}

function getChipLabel(
  id: string,
  promises?: PromisesSection | null,
  numbers?: NumbersSection | null,
  snapshot?: SnapshotSection | null
): string {
  if (id === "P_READ") return "Executive read";

  // Target IDs: T1, T2, ...
  if (id.startsWith("T")) {
    const verdict = promises?.verdicts?.find((v) => v.id === id);
    const target = promises?.targets?.find((t) => t.id === id);
    const pText = verdict?.promise || target?.statement || "";
    const metric = target?.metric || "";
    const textLower = pText.toLowerCase();
    const metricLower = metric.toLowerCase();

    if (textLower.includes("disbursal") || metricLower.includes("disbursal")) return "Disbursal guidance";
    if (textLower.includes("cost of funds") || textLower.includes("cost of borrowing") || metricLower.includes("cost_of_funds")) return "Cost of funds guidance";
    if (textLower.includes("credit cost") || metricLower.includes("credit_cost")) return "Credit cost guidance";
    if (textLower.includes("spread")) return "Spread guidance";
    if (textLower.includes("nim") || metricLower.includes("nim")) return "NIM guidance";
    if (textLower.includes("aum") || metricLower.includes("aum")) return "AUM growth target";
    if (textLower.includes("branch") || textLower.includes("store") || metricLower.includes("store")) return "Branch target";
    if (textLower.includes("capex") || metricLower.includes("capex")) return "Capex guidance";
    if (textLower.includes("it hardware") || metricLower.includes("it_hardware")) return "IT hardware target";
    if (textLower.includes("telecom") || metricLower.includes("telecom")) return "Telecom target";
    if (textLower.includes("mobile") || metricLower.includes("mobile")) return "Mobile target";
    if (textLower.includes("camera")) return "Camera module target";
    if (textLower.includes("lighting")) return "Lighting target";
    if (textLower.includes("order book") || metricLower.includes("order_book")) return "Order book target";
    if (textLower.includes("margin") || textLower.includes("ebitda") || metricLower.includes("margin")) return "Margin guidance";
    if (textLower.includes("pat") || textLower.includes("profit") || metricLower.includes("pat")) return "PAT target";
    if (textLower.includes("revenue") || textLower.includes("sales") || textLower.includes("topline") || metricLower.includes("revenue")) return "Revenue target";
    if (textLower.includes("volume") || metricLower.includes("volume")) return "Volume target";
    if (textLower.includes("cagr")) return "CAGR target";

    if (pText.includes("50% growth")) return "50% growth promise";
    if (pText.includes("56,000")) return "₹56,000 cr target";
    if (pText.includes("1,200") || pText.includes("1200")) return "₹1,200 cr target";

    if (metric) {
      return `${metric.replace(/_/g, " ")} promise`;
    }
    const words = pText.split(/\s+/).slice(0, 3).join(" ");
    return words ? `"${words}…"` : "Promise";
  }

  const snap = numbers?.snapshot;
  const qQuarter = snap?.latest_quarter_pat?.quarter || snap?.latest_operating_margin?.quarter || "Jun 2026";

  if (id === "N_OPM_LATEST") return `Margin, ${qQuarter} qtr`;
  if (id === "N_REV_LATEST") return `Revenue, ${qQuarter} qtr`;
  if (id === "N_PAT_LATEST") return `PAT, ${qQuarter} qtr`;
  if (id === "N_TTM_REV") return "TTM revenue";
  if (id === "N_TTM_PAT") return "TTM PAT";
  if (id === "N_DEBT_TO_EQUITY") return "Debt-to-equity";
  if (id === "N_BORROWINGS") return "Borrowings";
  if (id === "N_CCC_DAYS") return "Cash conversion cycle";
  if (id === "N_WC_DAYS") return "Working capital days";
  if (id === "N_CASH_CONV_3Y") return "3-yr cash conversion";
  if (id === "N_REV_CAGR_3Y") return "3-yr revenue CAGR";
  if (id === "N_REV_CAGR_5Y") return "5-yr revenue CAGR";
  if (id === "N_PAT_CAGR_3Y") return "3-yr PAT CAGR";
  if (id === "N_PAT_CAGR_5Y") return "5-yr PAT CAGR";

  if (id.startsWith("N_FLAG_")) {
    const idx = parseInt(id.replace("N_FLAG_", ""), 10) - 1;
    const flagObj = numbers?.flags?.[idx];
    if (flagObj?.flag === "profit_grew_far_faster_than_operations") {
      return "Profit vs operations flag";
    }
    if (flagObj?.flag === "cash_conversion_lt_70") {
      return "Cash conversion flag";
    }
    return "Balance sheet flag";
  }

  if (id.startsWith("S_SEG_")) {
    const idx = parseInt(id.replace("S_SEG_", ""), 10) - 1;
    const seg = snapshot?.segments?.[idx];
    const arPage = seg?.page || snapshot?.pages_used?.[0] || 75;
    return `Segment mix (AR p.${arPage})`;
  }

  if (id === "S_WHAT") return "Business overview";
  if (id === "S_CUSTOMERS") return "Customers & markets";

  return id;
}

export function BullBearSection({
  bullBear,
  promises,
  numbers,
  snapshot,
}: BullBearSectionProps) {
  if (!bullBear) return null;

  const { bull = [], bear = [] } = bullBear;
  if (bull.length === 0 && bear.length === 0) return null;

  const handleChipClick = (id: string) => {
    if (typeof window === "undefined") return;

    // Check if element with this ID exists on page
    const targetEl = document.getElementById(id);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: "smooth", block: "center" });

      // Highlight temporarily
      targetEl.classList.add("ring-2", "ring-amber-500", "transition-all");
      setTimeout(() => {
        targetEl.classList.remove("ring-2", "ring-amber-500");
      }, 2000);

      // If it's an unexpanded promise or details, click it to open
      if (id.startsWith("T") && !targetEl.classList.contains("shadow-xs")) {
        targetEl.click();
      }
    }
  };

  return (
    <section aria-labelledby="bull-bear-heading" className="space-y-3 pt-2">
      <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
        <h2
          id="bull-bear-heading"
          className="text-xs font-mono font-bold uppercase tracking-wider text-neutral-700 dark:text-neutral-300"
        >
          Bull vs Bear
        </h2>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          Grounded arguments
        </span>
      </div>

      <div className="space-y-3">
        {/* Bull Block */}
        {bull.length > 0 && (
          <div className="p-3 rounded border border-emerald-200/80 dark:border-emerald-900/50 bg-emerald-50/30 dark:bg-emerald-950/20 space-y-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-800 dark:text-emerald-400">
                Bull Thesis
              </span>
              <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-500">
                ({bull.length} points)
              </span>
            </div>

            <div className="space-y-2">
              {bull.map((item, idx) => (
                <div key={idx} className="space-y-1 text-xs leading-relaxed text-neutral-800 dark:text-neutral-200">
                  <div className="flex items-start gap-1.5">
                    <span className="text-emerald-600 dark:text-emerald-400 select-none font-bold">
                      +
                    </span>
                    <div className="flex-1">
                      <span>{item.point}</span>{" "}
                      {item.ids && item.ids.length > 0 && (
                        <span className="inline-flex items-center gap-1 flex-wrap ml-1 align-baseline">
                          {item.ids.map((id) => (
                            <button
                              key={id}
                              type="button"
                              onClick={() => handleChipClick(id)}
                              className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.2 rounded bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors cursor-pointer select-none"
                              title={`Jump to ${getChipLabel(id, promises, numbers, snapshot)}`}
                            >
                              <span>{getChipLabel(id, promises, numbers, snapshot)}</span>
                              <span className="text-[9px] text-neutral-400">↗</span>
                            </button>
                          ))}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bear Block */}
        {bear.length > 0 && (
          <div className="p-3 rounded border border-rose-200/80 dark:border-rose-900/50 bg-rose-50/30 dark:bg-rose-950/20 space-y-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-rose-800 dark:text-rose-400">
                Bear Thesis
              </span>
              <span className="text-[10px] font-mono text-rose-600 dark:text-rose-500">
                ({bear.length} points)
              </span>
            </div>

            <div className="space-y-2">
              {bear.map((item, idx) => (
                <div key={idx} className="space-y-1 text-xs leading-relaxed text-neutral-800 dark:text-neutral-200">
                  <div className="flex items-start gap-1.5">
                    <span className="text-rose-600 dark:text-rose-400 select-none font-bold">
                      −
                    </span>
                    <div className="flex-1">
                      <span>{item.point}</span>{" "}
                      {item.ids && item.ids.length > 0 && (
                        <span className="inline-flex items-center gap-1 flex-wrap ml-1 align-baseline">
                          {item.ids.map((id) => (
                            <button
                              key={id}
                              type="button"
                              onClick={() => handleChipClick(id)}
                              className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.2 rounded bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors cursor-pointer select-none"
                              title={`Jump to ${getChipLabel(id, promises, numbers, snapshot)}`}
                            >
                              <span>{getChipLabel(id, promises, numbers, snapshot)}</span>
                              <span className="text-[9px] text-neutral-400">↗</span>
                            </button>
                          ))}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
