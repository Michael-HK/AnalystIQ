export type CreditRatingJobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface CreditRatingLog {
  timestamp: string;
  phase: string;
  message: string;
  data?: unknown;
}

export interface CreditRatingJob {
  job_id: string;
  ticker: string;
  agencies: string[];
  start_year: number;
  end_year: number;
  period_label?: string;
  status: CreditRatingJobStatus;
  phase: string;
  progress: number;
  created_at: string;
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  company_name?: string | null;
  generated_data: {
    agencies?: string[];
    web_queries?: string[];
    comparison_paragraphs?: string[];
    comparison_table_markdown?: string;
  };
  reference_links?: Record<
    string,
    {
      url: string;
      title: string;
      domain: string;
    }
  >;
  artifacts?: {
    doc_ready: boolean;
    pdf_ready: boolean;
    doc_path?: string | null;
    pdf_path?: string | null;
  };
  log_count: number;
}

export interface CreditRatingOptions {
  tickers: string[];
  agencies: string[];
  year_options: number[];
  default_start_year: number;
  default_end_year: number;
}

export function formatCreditPeriodLabel(startYear: number, endYear: number): string {
  if (startYear === endYear) {
    return String(startYear);
  }
  return `${startYear}–${endYear}`;
}
