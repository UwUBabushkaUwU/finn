import { PersonEnrichment } from "@/lib/types";

interface PeopleBlockProps {
  people: PersonEnrichment[];
  companyName: string;
}

function formatDate(dateStr?: string | null): string | null {
  if (!dateStr) return null;
  try {
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      const d = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])));
      return d.toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      });
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

function extractDomain(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return "source";
  }
}

export function PeopleBlock({ people, companyName }: PeopleBlockProps) {
  // Only show top-role people
  const topPeople = people.filter((p) => p.is_top_role);

  if (topPeople.length === 0) {
    return null;
  }

  return (
    <div className="mt-2.5 space-y-2 pt-2 border-t border-neutral-150 dark:border-neutral-800">
      {topPeople.map((person, idx) => {
        const formattedDate = formatDate(person.effective_date);
        const isAppointed = (person.change || "").toLowerCase() === "appointed";
        const linkedInSearchUrl = `https://www.google.com/search?q=${encodeURIComponent(
          `"${person.name}" ${companyName} linkedin`
        )}`;

        return (
          <div
            key={`${person.name}-${idx}`}
            className="p-2 rounded bg-neutral-50/70 dark:bg-neutral-850/50 border border-neutral-200/70 dark:border-neutral-800 text-xs"
          >
            {/* Header: Name (bold), role, change, effective date */}
            <div className="leading-snug">
              <span className="font-bold text-neutral-950 dark:text-neutral-50">
                {person.name}
              </span>
              <span className="text-neutral-500 dark:text-neutral-400 mx-1.5">·</span>
              <span className="text-neutral-700 dark:text-neutral-300 font-medium">
                {person.role}
              </span>
              <span className="text-neutral-500 dark:text-neutral-400 mx-1.5">·</span>
              <span className="capitalize text-neutral-600 dark:text-neutral-400">
                {person.change}
              </span>
              {formattedDate && (
                <>
                  <span className="text-neutral-400 dark:text-neutral-500 mx-1">from</span>
                  <span className="font-mono text-[11px] text-neutral-600 dark:text-neutral-400">
                    {formattedDate}
                  </span>
                </>
              )}
            </div>

            {/* Bio or Missing Bio */}
            <div className="mt-1 text-[11px] text-neutral-600 dark:text-neutral-400 leading-relaxed">
              {person.bio ? (
                <div>
                  <span>{person.bio}</span>{" "}
                  <span className="text-neutral-400 dark:text-neutral-500 text-[10px]">
                    {person.bio_source === "filing" ? (
                      "(from the filing)"
                    ) : person.bio_source && person.bio_source.startsWith("http") ? (
                      <>
                        (
                        <a
                          href={person.bio_source}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="underline decoration-neutral-300 dark:decoration-neutral-600 hover:text-neutral-900 dark:hover:text-neutral-100"
                        >
                          {extractDomain(person.bio_source)} ↗
                        </a>
                        )
                      </>
                    ) : (
                      person.bio_source && `(${person.bio_source})`
                    )}
                  </span>
                </div>
              ) : isAppointed ? (
                <div className="text-neutral-500 dark:text-neutral-400 text-[10px] font-mono">
                  <span>No background in the filing</span>
                  <span className="mx-1.5">·</span>
                  <a
                    href={linkedInSearchUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="font-semibold text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    Search LinkedIn ↗
                  </a>
                </div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
