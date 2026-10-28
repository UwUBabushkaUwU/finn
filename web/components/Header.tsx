interface HeaderProps {
  todayDate: string;
  attentionCount: number;
  worthKnowingCount: number;
  routineCount: number;
}

export function Header({
  todayDate,
  attentionCount,
  worthKnowingCount,
  routineCount,
}: HeaderProps) {
  return (
    <header className="border-b border-neutral-200 dark:border-neutral-800 pb-3 pt-1">
      <div className="flex items-baseline justify-between gap-2">
        <h1 className="text-2xl font-black tracking-tight text-neutral-900 dark:text-neutral-50 font-serif">
          FINN
        </h1>
        <span className="text-xs font-mono tabular-nums uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          {todayDate}
        </span>
      </div>
      <div className="mt-1 text-xs text-neutral-600 dark:text-neutral-400 font-mono tabular-nums">
        <span className={attentionCount > 0 ? "font-semibold text-amber-700 dark:text-amber-500" : ""}>
          {attentionCount} need attention
        </span>
        <span className="mx-1.5 opacity-40">·</span>
        <span>{worthKnowingCount} worth knowing</span>
        <span className="mx-1.5 opacity-40">·</span>
        <span className="opacity-75">{routineCount} routine hidden</span>
      </div>
    </header>
  );
}
