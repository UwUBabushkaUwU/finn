"use client";

import { BullBearSection as BullBearData } from "@/lib/company";

interface BullBearSectionProps {
  bullBear?: BullBearData | null;
}

export function BullBearSection({ bullBear }: BullBearSectionProps) {
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
                              className="inline-block text-[10px] font-mono px-1 py-0.2 rounded bg-neutral-200/80 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-300 dark:hover:bg-neutral-700 transition-colors cursor-pointer select-none"
                              title={`Jump to ${id}`}
                            >
                              [{id}]
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
                              className="inline-block text-[10px] font-mono px-1 py-0.2 rounded bg-neutral-200/80 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-300 dark:hover:bg-neutral-700 transition-colors cursor-pointer select-none"
                              title={`Jump to ${id}`}
                            >
                              [{id}]
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
