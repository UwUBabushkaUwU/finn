import { PromisesSection, mapVerdictToGroup } from "@/lib/company";

interface ManagementHeroProps {
  promises?: PromisesSection | null;
}

export function ManagementHero({ promises }: ManagementHeroProps) {
  const verdicts = promises?.verdicts || [];
  const read = promises?.read;

  // Count by 5 plain groups
  let keptCount = 0;
  let brokenCount = 0;
  let inProgressCount = 0;
  let tooEarlyCount = 0;
  let cantVerifyCount = 0;

  // Breakdown within in_progress for coloring
  let behindCount = 0;
  let otherProgressCount = 0;

  for (const v of verdicts) {
    const group = mapVerdictToGroup(v.verdict);
    const norm = v.verdict.toLowerCase().trim();

    if (group === "kept") {
      keptCount++;
    } else if (group === "broken") {
      brokenCount++;
    } else if (group === "in_progress") {
      inProgressCount++;
      if (norm === "behind") {
        behindCount++;
      } else {
        otherProgressCount++;
      }
    } else if (group === "too_early") {
      tooEarlyCount++;
    } else {
      cantVerifyCount++;
    }
  }

  const total = verdicts.length;

  // Proportions for segmented bar (minimum width so segments are visible if >0)
  const keptPct = total > 0 ? (keptCount / total) * 100 : 0;
  const brokenPct = total > 0 ? (brokenCount / total) * 100 : 0;
  const behindPct = total > 0 ? (behindCount / total) * 100 : 0;
  const otherProgressPct = total > 0 ? (otherProgressCount / total) * 100 : 0;
  const tooEarlyPct = total > 0 ? (tooEarlyCount / total) * 100 : 0;
  const cantVerifyPct = total > 0 ? (cantVerifyCount / total) * 100 : 0;

  const legendParts: string[] = [
    `${keptCount} kept`,
    `${brokenCount} broken`,
    `${inProgressCount} in progress`,
    `${tooEarlyCount} too early`,
    `${cantVerifyCount} can't verify`,
  ];
  const legendText = legendParts.join(" · ");

  return (
    <section aria-labelledby="hero-delivery-heading" className="space-y-3 pt-1">
      {/* Title */}
      <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
        <h2
          id="hero-delivery-heading"
          className="text-sm font-mono font-bold tracking-tight text-neutral-900 dark:text-neutral-100 uppercase"
        >
          Did management deliver?
        </h2>
        <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500 tabular-nums">
          {total} targets tracked
        </span>
      </div>

      {/* Segmented Horizontal Bar */}
      <div className="space-y-1.5">
        <div
          role="progressbar"
          aria-label="Target delivery breakdown"
          className="h-3 w-full rounded-sm overflow-hidden flex bg-neutral-100 dark:bg-neutral-800 border border-neutral-200/80 dark:border-neutral-800"
        >
          {keptPct > 0 && (
            <div
              style={{ width: `${keptPct}%` }}
              title={`${keptCount} Kept`}
              className="h-full bg-emerald-600 dark:bg-emerald-500 transition-all border-r border-background/20 last:border-0"
            />
          )}
          {brokenPct > 0 && (
            <div
              style={{ width: `${brokenPct}%` }}
              title={`${brokenCount} Broken`}
              className="h-full bg-rose-600 dark:bg-rose-500 transition-all border-r border-background/20 last:border-0"
            />
          )}
          {behindPct > 0 && (
            <div
              style={{ width: `${behindPct}%` }}
              title={`${behindCount} Behind`}
              className="h-full bg-amber-500 dark:bg-amber-400 transition-all border-r border-background/20 last:border-0"
            />
          )}
          {otherProgressPct > 0 && (
            <div
              style={{ width: `${otherProgressPct}%` }}
              title={`${otherProgressCount} Ahead or On track`}
              className="h-full bg-neutral-400 dark:bg-neutral-600 transition-all border-r border-background/20 last:border-0"
            />
          )}
          {tooEarlyPct > 0 && (
            <div
              style={{ width: `${tooEarlyPct}%` }}
              title={`${tooEarlyCount} Too early`}
              className="h-full bg-neutral-300 dark:bg-neutral-700 transition-all border-r border-background/20 last:border-0"
            />
          )}
          {cantVerifyPct > 0 && (
            <div
              style={{ width: `${cantVerifyPct}%` }}
              title={`${cantVerifyCount} Can't verify`}
              className="h-full bg-neutral-200 dark:bg-neutral-800 transition-all"
            />
          )}
        </div>

        {/* Legend in words */}
        <p className="text-[11px] font-mono text-neutral-600 dark:text-neutral-400">
          {legendText}
        </p>
      </div>

      {/* Post-override read (2 sentences) */}
      {read && (
        <div
          id="P_READ"
          className="p-3 rounded border border-neutral-200/90 dark:border-neutral-800/90 bg-neutral-50/60 dark:bg-neutral-900/50 border-l-2 border-l-neutral-700 dark:border-l-neutral-300"
        >
          <p className="text-[13px] leading-relaxed text-neutral-800 dark:text-neutral-200 font-serif italic">
            {read}
          </p>
        </div>
      )}
    </section>
  );
}

