export default function ResearchLoading() {
  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800 animate-pulse">
      <div className="mx-auto max-w-xl px-4 py-4 sm:px-6 space-y-4">
        {/* Header Skeleton */}
        <header className="border-b border-neutral-200 dark:border-neutral-800 pb-3 space-y-2">
          <div className="flex items-baseline justify-between">
            <div className="h-3 w-28 bg-neutral-200 dark:bg-neutral-800 rounded" />
            <div className="h-3 w-16 bg-neutral-200 dark:bg-neutral-800 rounded" />
          </div>
          <div className="h-8 w-36 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="h-3 w-64 bg-neutral-200 dark:bg-neutral-800 rounded" />
        </header>

        {/* Search Bar Skeleton */}
        <div className="h-12 w-full rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60" />

        {/* Company List Skeletons */}
        <div className="space-y-2.5 pt-2">
          <div className="h-3 w-32 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 divide-y divide-neutral-100 dark:divide-neutral-800/60">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="p-3.5 space-y-2">
                <div className="flex items-baseline justify-between">
                  <div className="flex items-center gap-2">
                    <div className="h-4 w-20 bg-neutral-200 dark:bg-neutral-800 rounded" />
                    <div className="h-3.5 w-32 bg-neutral-200 dark:bg-neutral-800 rounded" />
                  </div>
                  <div className="h-3 w-14 bg-neutral-200 dark:bg-neutral-800 rounded" />
                </div>
                <div className="h-1.5 w-full bg-neutral-200 dark:bg-neutral-800 rounded-full" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

