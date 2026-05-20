import { useEffect, useMemo, useState } from "react";
import { ArtifactPanel } from "@/features/artifacts/artifact-panel";
import { ReportConfigPanel } from "@/features/report-config/report-config-panel";
import { ActivityTimeline } from "@/features/report-runner/activity-timeline";
import { ResearchPanels } from "@/features/report-runner/research-panels";
import { SnapshotPanel } from "@/features/report-runner/snapshot-panel";
import { StatusStrip } from "@/features/report-runner/status-strip";
import { ReportViewerDialog } from "@/features/report-viewer/report-viewer-dialog";
import { CreditRatingWorkspace } from "@/features/credit-rating/credit-rating-workspace";
import { cancelReportJob, createReportJob, generatePptx, getOptions, getReportJob, subscribeToJobEvents } from "@/lib/api";
import type { ReportJob, ReportLog, ReportOptions, ReportType } from "@/types/report";

function App() {
  const [workspace, setWorkspace] = useState<"report" | "credit-rating">("report");
  const [options, setOptions] = useState<ReportOptions | null>(null);
  const [ticker, setTicker] = useState<string>("");
  const [reportType, setReportType] = useState<ReportType>("investment");
  const [presentationStyle, setPresentationStyle] = useState<string>("Institutional Light");
  const [customInstruction, setCustomInstruction] = useState<string>("");
  const [job, setJob] = useState<ReportJob | null>(null);
  const [logs, setLogs] = useState<ReportLog[]>([]);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isGeneratingPptx, setIsGeneratingPptx] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOptions()
      .then((data) => {
        setOptions(data);
        setTicker(data.tickers[0] ?? "");
        setPresentationStyle(data.presentation_styles[0] ?? "Institutional Light");
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!job?.job_id) return;
    let stopped = false;

    const stopRealtime = () => {
      if (stopped) return;
      stopped = true;
      unsubscribe();
      clearInterval(interval);
    };

    const unsubscribe = subscribeToJobEvents(
      job.job_id,
      (log) => setLogs((prev) => [...prev, log]),
      (evtError) => setError(evtError.message)
    );
    const interval = setInterval(async () => {
      try {
        const latest = await getReportJob(job.job_id);
        setJob(latest);
        setError((current) => (current && current.toLowerCase().includes("stream") ? null : current));
        if (latest.status === "failed" && latest.error) {
          setError(latest.error);
        }
      } catch (pollError) {
        const message = (pollError as Error).message;
        if (
          message.includes("ECONNREFUSED") ||
          message.toLowerCase().includes("socket hang up") ||
          message.toLowerCase().includes("failed to fetch") ||
          message.toLowerCase().includes("job not found")
        ) {
          setJob(null);
          setLogs([]);
          setError("Backend API is unavailable. Please ensure the server is running on port 8000.");
          stopRealtime();
          return;
        }
        setError(message);
      }
    }, 1500);

    return () => {
      stopRealtime();
    };
  }, [job?.job_id]);

  const isRunning = useMemo(() => job?.status === "running" || job?.status === "queued", [job?.status]);
  const showEngagementBeam = isRunning || isGeneratingPptx;
  const runningFocusText = useMemo(() => {
    if (isGeneratingPptx) {
      return "EXPORT: Generating editable PowerPoint presentation from your completed report...";
    }
    if (!logs.length) {
      return "AnalystIQ is researching market signals, validating financial context, and composing your report...";
    }
    const latest = logs[logs.length - 1];
    const cleanMessage = latest.message
      .replace(/[\p{Extended_Pictographic}\uFE0F]/gu, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!cleanMessage) {
      return "AnalystIQ is processing your report.";
    }
    const phaseLabel = latest.phase ? latest.phase.toUpperCase() : "STATUS";
    return `${phaseLabel}: ${cleanMessage}`;
  }, [isGeneratingPptx, logs]);

  const handleGenerate = async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    setLogs([]);
    try {
      const created = await createReportJob({
        ticker,
        reportType,
        customInstruction,
        pipeline: "v1",
        presentationStyle,
      });
      setJob(created);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!job) return;
    await cancelReportJob(job.job_id);
  };

  const handleGeneratePptx = async () => {
    if (!job) return;
    setIsGeneratingPptx(true);
    setError(null);
    try {
      await generatePptx(job.job_id);
      const latest = await getReportJob(job.job_id);
      setJob(latest);
    } catch (pptError) {
      setError((pptError as Error).message);
    } finally {
      setIsGeneratingPptx(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 via-slate-50 to-white px-4 py-6">
      <div className="mx-auto w-full max-w-[1700px] space-y-4">
        <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-panel">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setWorkspace("report")}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                workspace === "report"
                  ? "bg-blue-600 text-white"
                  : "border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
              }`}
            >
              Report Workspace
            </button>
            <button
              type="button"
              onClick={() => setWorkspace("credit-rating")}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                workspace === "credit-rating"
                  ? "bg-blue-600 text-white"
                  : "border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
              }`}
            >
              Credit Rating Workspace
            </button>
          </div>
        </section>

        {workspace === "credit-rating" ? (
          <CreditRatingWorkspace />
        ) : (
          <>
            <section className="rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-blue-50 p-6 shadow-panel">
              <div className="mb-4 flex items-center gap-3">
                <span className="rounded-full border border-blue-200 bg-blue-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-blue-700">
                  AnalystIQ
                </span>
                <span className="text-sm font-medium text-slate-500">Institutional Research Workspace</span>
              </div>
              <h2 className="text-3xl font-semibold tracking-tight text-slate-900">AnalystIQ Studio</h2>
              <p className="mt-4 max-w-4xl text-lg leading-8 text-slate-600">
                Built for analyst teams to move from ticker selection to decision-ready materials across investment and credit workflows.
              </p>
              <ul className="mt-5 list-disc space-y-2 pl-8 text-base text-slate-700">
                <li>
                  <span className="font-semibold">Dual report modes:</span> Generate either an <span className="font-semibold">Investment Report</span> or a{" "}
                  <span className="font-semibold">Credit Analysis Report</span> for the selected company.
                </li>
                <li>
                  <span className="font-semibold">Decision-ready insights:</span> Review executive summary and key highlights in-app before exporting deliverables.
                </li>
                <li>
                  <span className="font-semibold">Editable presentation export:</span> Create and download a{" "}
                  <span className="font-semibold">.pptx</span> deck (up to 10 slides) for internal review meetings.
                </li>
              </ul>
              <p className="mt-5 border-t border-slate-200 pt-4 text-base text-slate-700">
                <span className="font-semibold">How to navigate:</span> Select a ticker and report type in the sidebar, click{" "}
                <span className="font-semibold">Generate Report</span>, follow the <span className="font-semibold">Research Journey</span>, review the{" "}
                <span className="font-semibold">Report Snapshot</span>, then download the PDF and optional editable PowerPoint.
              </p>
            </section>

            {showEngagementBeam ? (
              <section className="overflow-hidden rounded-xl border border-blue-200 bg-blue-50/70 p-3">
                <div className="running-beam h-2 rounded-full" />
                <p className="marquee-text mt-2 text-sm font-medium text-blue-700">{runningFocusText}</p>
              </section>
            ) : null}

            <StatusStrip job={job} />

            {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

            <div className="grid gap-4 xl:grid-cols-[320px,1fr,360px]">
              <ReportConfigPanel
                options={options}
                ticker={ticker}
                reportType={reportType}
                customInstruction={customInstruction}
                presentationStyle={presentationStyle}
                isRunning={isRunning || loading}
                onTickerChange={setTicker}
                onReportTypeChange={setReportType}
                onCustomInstructionChange={setCustomInstruction}
                onPresentationStyleChange={setPresentationStyle}
                onGenerate={handleGenerate}
                onCancel={handleCancel}
              />

              <div className="space-y-4">
                <ArtifactPanel
                  job={job}
                  onGeneratePptx={handleGeneratePptx}
                  isGeneratingPptx={isGeneratingPptx}
                  onOpenViewer={() => setViewerOpen(true)}
                />
                <ResearchPanels job={job} />
                <SnapshotPanel job={job} />
              </div>

              <ActivityTimeline logs={logs} />
            </div>
          </>
        )}
      </div>
      {workspace === "report" ? <ReportViewerDialog open={viewerOpen} onOpenChange={setViewerOpen} jobId={job?.job_id} /> : null}
    </main>
  );
}

export default App;
