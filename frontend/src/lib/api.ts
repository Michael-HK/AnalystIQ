import type { ReportJob, ReportLog, ReportOptions, ReportType } from "@/types/report";
import type { CreditRatingJob, CreditRatingLog, CreditRatingOptions } from "@/types/credit-rating";

const API_BASE = import.meta.env.VITE_ANALYSTIQ_API_BASE ?? "/api";

interface CreateJobInput {
  ticker: string;
  reportType: ReportType;
  customInstruction?: string;
  pipeline: "v1" | "v3";
  presentationStyle: string;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function getOptions(): Promise<ReportOptions> {
  const res = await fetch(`${API_BASE}/reports/options`);
  return readJson<ReportOptions>(res);
}

export async function createReportJob(input: CreateJobInput): Promise<ReportJob> {
  const res = await fetch(`${API_BASE}/reports/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker: input.ticker,
      report_type: input.reportType,
      custom_instruction: input.customInstruction || null,
      pipeline: input.pipeline,
      presentation_style: input.presentationStyle,
    }),
  });
  return readJson<ReportJob>(res);
}

export async function getReportJob(jobId: string): Promise<ReportJob> {
  const res = await fetch(`${API_BASE}/reports/jobs/${jobId}`);
  return readJson<ReportJob>(res);
}

export async function cancelReportJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  await readJson(res);
}

export async function generatePptx(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/reports/jobs/${jobId}/pptx`, { method: "POST" });
  await readJson(res);
}

export function subscribeToJobEvents(
  jobId: string,
  onLog: (log: ReportLog) => void,
  onError?: (error: Error) => void
): () => void {
  const source = new EventSource(`${API_BASE}/reports/jobs/${jobId}/events`);
  source.addEventListener("progress", (evt) => {
    try {
      const parsed = JSON.parse((evt as MessageEvent).data) as { payload: ReportLog };
      onLog(parsed.payload);
    } catch (error) {
      if (onError) onError(error as Error);
    }
  });
  source.addEventListener("error", () => {
    // EventSource auto-reconnects by design; transient drops are expected.
    // We rely on polling for authoritative state, so only notify on hard-close.
    if (source.readyState === EventSource.CLOSED && onError) {
      onError(new Error("Live stream disconnected."));
    }
  });
  return () => source.close();
}

export function artifactUrl(jobId: string, artifactType: "md" | "pdf" | "pptx") {
  return `${API_BASE}/reports/jobs/${jobId}/artifacts/${artifactType}`;
}

export function viewerUrl(jobId: string) {
  return `${API_BASE}/reports/jobs/${jobId}/viewer`;
}

interface CreateCreditRatingJobInput {
  ticker: string;
  agencies: string[];
  startYear: number;
  endYear: number;
}

export async function getCreditRatingOptions(): Promise<CreditRatingOptions> {
  const res = await fetch(`${API_BASE}/credit-rating/options`);
  return readJson<CreditRatingOptions>(res);
}

export async function createCreditRatingJob(input: CreateCreditRatingJobInput): Promise<CreditRatingJob> {
  const res = await fetch(`${API_BASE}/credit-rating/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker: input.ticker,
      agencies: input.agencies,
      start_year: input.startYear,
      end_year: input.endYear,
    }),
  });
  return readJson<CreditRatingJob>(res);
}

export async function getCreditRatingJob(jobId: string): Promise<CreditRatingJob> {
  const res = await fetch(`${API_BASE}/credit-rating/jobs/${jobId}`);
  return readJson<CreditRatingJob>(res);
}

export async function cancelCreditRatingJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/credit-rating/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  await readJson(res);
}

export function subscribeToCreditRatingJobEvents(
  jobId: string,
  onLog: (log: CreditRatingLog) => void,
  onError?: (error: Error) => void
): () => void {
  const source = new EventSource(`${API_BASE}/credit-rating/jobs/${jobId}/events`);
  source.addEventListener("progress", (evt) => {
    try {
      const parsed = JSON.parse((evt as MessageEvent).data) as { payload: CreditRatingLog };
      onLog(parsed.payload);
    } catch (error) {
      if (onError) onError(error as Error);
    }
  });
  source.addEventListener("error", () => {
    if (source.readyState === EventSource.CLOSED && onError) {
      onError(new Error("Live stream disconnected."));
    }
  });
  return () => source.close();
}

export function creditRatingArtifactUrl(jobId: string, artifactType: "doc" | "pdf") {
  return `${API_BASE}/credit-rating/jobs/${jobId}/artifacts/${artifactType}`;
}
