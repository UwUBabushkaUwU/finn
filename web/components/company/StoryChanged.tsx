import { GuidanceTimelineSection, parseRevisedTimeline } from "@/lib/company";

interface StoryChangedProps {
  guidanceTimeline?: GuidanceTimelineSection | null;
}

export function StoryChanged({ guidanceTimeline }: StoryChangedProps) {
  const timelineList = guidanceTimeline?.timeline || [];
  const revisedTargets = parseRevisedTimeline(timelineList);

  if (revisedTargets.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="story-changed-heading" className="space-y-2 pt-2">
      <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
        <h2
          id="story-changed-heading"
          className="text-xs font-mono font-bold uppercase tracking-wider text-amber-700 dark:text-amber-500"
        >
          How the story changed ({revisedTargets.length})
        </h2>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
          Revised guidance tracking
        </span>
      </div>

      <div className="space-y-2">
        {revisedTargets.map((item, idx) => (
          <div
            key={idx}
            className="p-2.5 rounded border border-neutral-200 dark:border-neutral-800/80 bg-neutral-50/50 dark:bg-neutral-900/40 space-y-2"
          >
            {/* Metric and period */}
            <div className="text-xs font-mono font-semibold text-neutral-900 dark:text-neutral-100 uppercase tracking-tight">
              {item.metricLabel}
            </div>

            {/* Chain of values by quarter */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {item.steps.map((step, sIdx) => (
                <div key={sIdx} className="flex items-center gap-1.5">
                  <div className="flex flex-col items-center min-w-[48px] px-2 py-1 rounded bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-center">
                    <span className="text-xs font-mono font-bold text-neutral-900 dark:text-neutral-100">
                      {step.value}
                    </span>
                    {step.quarter && (
                      <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 mt-0.5">
                        {step.quarter}
                      </span>
                    )}
                  </div>
                  {sIdx < item.steps.length - 1 && (
                    <span className="text-neutral-400 dark:text-neutral-500 text-xs font-mono font-bold select-none">
                      →
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

