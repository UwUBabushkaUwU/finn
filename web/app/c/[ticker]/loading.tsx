export default function CompanyLoading() {
  return (
    <main className="min-h-screen bg-[#fcfbf9] text-neutral-900 dark:bg-[#0c0d0e] dark:text-neutral-100 selection:bg-neutral-200 dark:selection:bg-neutral-800 animate-pulse">
      <div className="mx-auto max-w-xl px-4 py-4 sm:px-6 space-y-6">
        {/* Header Skeleton */}
        <div className="space-y-2 border-b border-neutral-200 dark:border-neutral-800 pb-4">
          <div className="flex items-baseline justify-between">
            <div className="h-4 w-24 bg-neutral-200 dark:bg-neutral-800 rounded" />
            <div className="h-3 w-16 bg-neutral-200 dark:bg-neutral-800 rounded" />
          </div>
          <div className="flex items-baseline justify-between pt-1">
            <div className="h-8 w-40 bg-neutral-200 dark:bg-neutral-800 rounded" />
            <div className="h-6 w-20 bg-neutral-200 dark:bg-neutral-800 rounded" />
          </div>
          <div className="h-3 w-60 bg-neutral-200 dark:bg-neutral-800 rounded" />
        </div>

        {/* Hero Segmented Bar Skeleton */}
        <div className="p-4 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 space-y-3">
          <div className="h-4 w-44 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="h-3 w-full bg-neutral-200 dark:bg-neutral-800 rounded-full" />
          <div className="h-3 w-48 bg-neutral-200 dark:bg-neutral-800 rounded" />
          <div className="h-14 w-full bg-neutral-100 dark:bg-neutral-800/40 rounded" />
        </div>

        {/* Promises Skeleton */}
        <div className="space-y-3">
          <div className="h-4 w-36 bg-neutral-200 dark:bg-neutral-800 rounded" />
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="p-4 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 space-y-2"
            >
              <div className="flex justify-between">
                <div className="h-3 w-24 bg-neutral-200 dark:bg-neutral-800 rounded" />
                <div className="h-4 w-16 bg-neutral-200 dark:bg-neutral-800 rounded" />
              </div>
              <div className="h-4 w-5/6 bg-neutral-200 dark:bg-neutral-800 rounded" />
              <div className="h-3 w-1/2 bg-neutral-200 dark:bg-neutral-800 rounded" />
            </div>
          ))}
        </div>

        {/* Numbers Skeleton */}
        <div className="grid grid-cols-2 gap-2">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="p-3 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 h-20"
            />
          ))}
        </div>
      </div>
    </main>
  );
}

