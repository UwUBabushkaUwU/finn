import { Company, Filing, GroupedEvent } from "./types";

const THREE_HOURS_MS = 3 * 60 * 60 * 1000;

export function formatCategory(cat?: string | null): string {
  if (!cat) return "Corporate";
  switch (cat.toLowerCase()) {
    case "results":
      return "Results";
    case "management_change":
      return "Mgmt Change";
    case "acquisition":
    case "m&a":
      return "M&A";
    case "regulatory":
      return "Regulatory";
    case "dividend":
      return "Dividend";
    case "credit_rating":
      return "Credit Rating";
    case "fundraising":
      return "Fundraising";
    case "board_meeting":
      return "Board Meeting";
    case "investor_update":
      return "Investor Call";
    case "unclassified":
      return "Corporate";
    default:
      return cat
        .split("_")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
  }
}

interface FilingCluster {
  ticker: string;
  filings: Filing[];
  earliestTime: number;
  latestTime: number;
}

export function groupFilingsIntoEvents(
  filings: Filing[],
  companiesMap: Record<string, Company>
): GroupedEvent[] {
  // 1. Sort filings newest to oldest
  const sorted = [...filings].sort(
    (a, b) => new Date(b.filed_at).getTime() - new Date(a.filed_at).getTime()
  );

  const clusters: FilingCluster[] = [];

  for (const filing of sorted) {
    const fTime = new Date(filing.filed_at).getTime();
    let matchedCluster: FilingCluster | undefined;

    for (const cluster of clusters) {
      if (cluster.ticker === filing.ticker) {
        // Check if filing time is within 3 hours of cluster range
        const withinEarliest = Math.abs(fTime - cluster.earliestTime) <= THREE_HOURS_MS;
        const withinLatest = Math.abs(fTime - cluster.latestTime) <= THREE_HOURS_MS;

        if (withinEarliest || withinLatest) {
          matchedCluster = cluster;
          break;
        }
      }
    }

    if (matchedCluster) {
      matchedCluster.filings.push(filing);
      matchedCluster.earliestTime = Math.min(matchedCluster.earliestTime, fTime);
      matchedCluster.latestTime = Math.max(matchedCluster.latestTime, fTime);
    } else {
      clusters.push({
        ticker: filing.ticker,
        filings: [filing],
        earliestTime: fTime,
        latestTime: fTime,
      });
    }
  }

  // 2. Convert each cluster into a GroupedEvent
  return clusters.map((cluster) => {
    // Determine card priority: highest filing priority (1 is highest, then 2, then 3)
    let cardPriority: 1 | 2 | 3 = 3;
    for (const f of cluster.filings) {
      const p = (f.priority ?? 3) as 1 | 2 | 3;
      if (p < cardPriority) {
        cardPriority = p;
      }
    }

    // Determine primary filing:
    // Sort cluster filings: priority asc, summary presence desc, filed_at desc
    const sortedCluster = [...cluster.filings].sort((a, b) => {
      const pA = a.priority ?? 3;
      const pB = b.priority ?? 3;
      if (pA !== pB) return pA - pB;

      const hasSummaryA = a.summary && a.summary.trim().length > 0 ? 1 : 0;
      const hasSummaryB = b.summary && b.summary.trim().length > 0 ? 1 : 0;
      if (hasSummaryA !== hasSummaryB) return hasSummaryB - hasSummaryA;

      return new Date(b.filed_at).getTime() - new Date(a.filed_at).getTime();
    });

    const primaryFiling = sortedCluster[0];
    const secondaryFilings = sortedCluster.slice(1);

    const headline = primaryFiling.summary?.trim() || primaryFiling.subject;
    const category = formatCategory(primaryFiling.category);
    const company = companiesMap[cluster.ticker];
    const companyName = company?.name || cluster.ticker;

    // Distinct categories in the group (max 3, e.g. M&A, RESULTS)
    const categorySet = new Set<string>();
    categorySet.add(category);
    for (const f of sortedCluster) {
      if (f.category) {
        categorySet.add(formatCategory(f.category));
      }
    }
    const categories = Array.from(categorySet).slice(0, 3);

    // Look for results enrichment in any filing in this cluster
    const resultsFiling = sortedCluster.find(
      (f) => f.enrichment?.results && f.enrichment.results.metrics
    );
    const resultsEnrichment = resultsFiling?.enrichment?.results || null;

    // Look for people enrichment in any filing in this cluster
    const peopleFiling = sortedCluster.find(
      (f) => f.enrichment?.people && f.enrichment.people.length > 0
    );
    const peopleEnrichment = peopleFiling?.enrichment?.people || null;

    // Use latest filing's timestamp in the cluster for event freshness
    const latestFiledAt = new Date(cluster.latestTime).toISOString();

    return {
      id: `${cluster.ticker}-${primaryFiling.id}`,
      ticker: cluster.ticker,
      companyName,
      priority: cardPriority,
      headline,
      category,
      categories,
      filedAt: latestFiledAt,
      attachmentUrl: primaryFiling.attachment_url || null,
      primaryFiling,
      secondaryFilings,
      resultsEnrichment,
      peopleEnrichment,
    };
  });
}
