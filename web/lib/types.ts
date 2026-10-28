export interface Company {
  ticker: string;
  name: string;
  sector?: string | null;
  size?: string | null;
  in_portfolio: boolean;
  is_research?: boolean;
}

export interface ResultsMetric {
  current?: number | null;
  previous_quarter?: number | null;
  year_ago?: number | null;
  qoq_pct?: number | null;
  qoq_label?: string | null;
  yoy_pct?: number | null;
  yoy_label?: string | null;
  margin_pct?: number | null;
  margin_change_pp?: number | null;
}

export interface ResultsEnrichment {
  basis?: string;
  unit?: string;
  periods?: {
    current?: string;
    previous_quarter?: string;
    year_ago?: string;
  };
  metrics?: {
    revenue?: ResultsMetric;
    ebitda?: ResultsMetric;
    pbt?: ResultsMetric;
    pat?: ResultsMetric;
    [key: string]: unknown;
  };
  associates_after_tax?: boolean;
  is_lender?: boolean;
  verified?: boolean;
  check?: boolean;
  page?: number | string | null;
  source_pdf_url?: string | null;
  check_diff?: number | null;
}

export interface PersonEnrichment {
  name: string;
  role: string;
  change: string;
  effective_date?: string | null;
  reason?: string | null;
  profile?: string | null;
  bio?: string | null;
  bio_source?: string | null;
  is_top_role: boolean;
}

export interface Filing {
  id: string;
  ticker: string;
  exchange: string;
  filed_at: string;
  subject: string;
  description?: string | null;
  attachment_url?: string | null;
  category?: string | null;
  priority?: number | null; // 1, 2, 3
  summary?: string | null;
  enrichment?: {
    why?: string;
    results?: ResultsEnrichment;
    people?: PersonEnrichment[];
    [key: string]: unknown;
  } | null;
  processed_at?: string | null;
}

export interface Alert {
  id: number;
  ticker: string;
  kind: "volume_spike" | "price_move" | "material_filing";
  message: string;
  value?: number | null;
  threshold?: number | null;
  filing_id?: string | null;
  trigger_date: string;
  seen: boolean;
}

export interface Price {
  ticker: string;
  date: string;
  close?: number | null;
  pct_change?: number | null;
  vol_ratio?: number | null;
}

export interface GroupedEvent {
  id: string;
  ticker: string;
  companyName: string;
  priority: 1 | 2 | 3;
  headline: string;
  category: string;
  categories: string[];
  filedAt: string;
  attachmentUrl: string | null;
  primaryFiling: Filing;
  secondaryFilings: Filing[];
  resultsEnrichment?: ResultsEnrichment | null;
  peopleEnrichment?: PersonEnrichment[] | null;
}
