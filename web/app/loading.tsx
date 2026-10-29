export default function BriefLoading() {
  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800 animate-pulse">
      <div className="mx-auto max-w-xl px-4 py-4 sm:px-6 space-y-4">
        {/* Header Skeleton */}
        <header className="border-b border-neutral-200 dark:border-neutral-800 pb-3 space-y-2">
          <div className="flex items-baseline justify-between">
            <div className="h-3 w-28 bg-neutral-200 dark:bg-neutral-800 rounded" />
            <div className="h-3 w-16 bg-neutral-200 dark:bg-neutral-800 rounded" />
          </div>
          <div className="h-8 w-44 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="h-3 w-56 bg-neutral-200 dark:bg-neutral-800 rounded" />
        </header>

        {/* Time Chips Skeleton */}
        <div className="flex gap-2">
          <div className="h-7 w-12 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="h-7 w-12 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="h-7 w-12 bg-neutral-200 dark:bg-neutral-800 rounded" />
        </div>

        {/* Alerts Strip Skeleton */}
        <div className="h-14 w-full bg-neutral-200/60 dark:bg-neutral-800/40 rounded border border-neutral-200 dark:border-neutral-800" />

        {/* Priority 1 (Needs Attention) Skeleton */}
        <section className="space-y-2.5 pt-1">
          <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
            <div className="h-3.5 w-36 bg-neutral-200 dark:bg-neutral-800 rounded" />
            <div className="h-2.5 w-20 bg-neutral-200 dark:bg-neutral-800 rounded" />
          </div>

          {[1, 2].map((i) => (
            <div
              key={i}
              className="p-4 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 space-y-2.5"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-4 w-20 bg-neutral-200 dark:bg-neutral-800 rounded" />
                  <div className="h-3.5 w-28 bg-neutral-200 dark:bg-neutral-800 rounded" />
                </div>
                <div className="h-4 w-16 bg-neutral-200 dark:bg-neutral-800 rounded" />
              </div>
              <div className="h-4 w-3/4 bg-neutral-200 dark:bg-neutral-800 rounded" />
              <div className="h-3 w-full bg-neutral-200 dark:bg-neutral-800 rounded" />
              <div className="h-3 w-5/6 bg-neutral-200 dark:bg-neutral-800 rounded" />
            </div>
          ))}
        </section>

        {/* Priority 2 (Worth Knowing) Skeleton */}
        <section className="space-y-2 pt-2">
          <div className="flex items-baseline justify-between border-b border-neutral-200 dark:border-neutral-800 pb-1">
            <div className="h-3.5 w-32 bg-neutral-200 dark:bg-neutral-800 rounded" />
            <div className="h-2.5 w-20 bg-neutral-200 dark:bg-neutral-800 rounded" />
          </div>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="p-3 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 flex items-center justify-between"
            >
              <div className="space-y-1.5 w-3/4">
                <div className="h-3.5 w-16 bg-neutral-200 dark:bg-neutral-800 rounded" />
                <div className="h-3 w-4/5 bg-neutral-200 dark:bg-neutral-800 rounded" />
              </div>
              <div className="h-3.5 w-12 bg-neutral-200 dark:bg-neutral-800 rounded" />
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
