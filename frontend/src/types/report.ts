export type ReportType = "investment" | "credit";

export type ReportJobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ReportLog {
  timestamp: string;
  phase: string;
  message: string;
  data?: unknown;
}

export interface ReportJob {
  job_id: string;
  ticker: string;
  report_type: ReportType;
  custom_instruction?: string | null;
  pipeline: "v1" | "v3";
  presentation_style: string;
  status: ReportJobStatus;
  phase: string;
  progress: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  company_name?: string | null;
  opening_section_preview?: string | null;
  executive_summary_preview?: string | null;
  key_points: string[];
  generated_data: {
    structure?: string[];
    web_queries?: string[];
    financial_queries?: Array<{ query: string; ticker: string }>;
  };
  reference_links?: Record<
    string,
    {
      url: string;
      title: string;
      domain: string;
    }
  >;
  artifacts: {
    markdown_ready: boolean;
    pdf_ready: boolean;
    ppt_ready: boolean;
    report_md_path?: string | null;
    pdf_path?: string | null;
    ppt_path?: string | null;
  };
  log_count: number;
}

export interface ReportOptions {
  tickers: string[];
  report_type_options: Record<string, ReportType>;
  presentation_styles: string[];
}
