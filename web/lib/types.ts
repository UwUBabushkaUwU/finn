export interface Company {
  ticker: string;
  name: string;
  sector?: string | null;
  size?: string | null;
  in_portfolio: boolean;
  is_research?: boolean;
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
  filedAt: string;
  attachmentUrl: string | null;
  primaryFiling: Filing;
  secondaryFilings: Filing[];
}
