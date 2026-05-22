import { useEffect, useMemo, useState } from "react";
import { ActivityTimeline } from "@/features/report-runner/activity-timeline";
import { CreditRatingConfigPanel } from "@/features/credit-rating/credit-rating-config-panel";
import { CreditRatingOutputPanel } from "@/features/credit-rating/credit-rating-output-panel";
import { CreditRatingStatusStrip } from "@/features/credit-rating/credit-rating-status-strip";
import {
  cancelCreditRatingJob,
  createCreditRatingJob,
  getCreditRatingJob,
  getCreditRatingOptions,
  subscribeToCreditRatingJobEvents,
} from "@/lib/api";
import type { CreditRatingJob, CreditRatingLog, CreditRatingOptions } from "@/types/credit-rating";

export function CreditRatingWorkspace() {
  const [options, setOptions] = useState<CreditRatingOptions | null>(null);
  const [ticker, setTicker] = useState("");
  const [selectedAgencies, setSelectedAgencies] = useState<string[]>([]);
  const [startYear, setStartYear] = useState(new Date().getFullYear());
  const [endYear, setEndYear] = useState(new Date().getFullYear());
  const [job, setJob] = useState<CreditRatingJob | null>(null);
  const [logs, setLogs] = useState<CreditRatingLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCreditRatingOptions()
      .then((data) => {
        setOptions(data);
        setTicker(data.tickers[0] ?? "");
        setSelectedAgencies(data.agencies.slice(0, 3));
        setStartYear(data.default_start_year);
        setEndYear(data.default_end_year);
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

    const unsubscribe = subscribeToCreditRatingJobEvents(
      job.job_id,
      (log) => setLogs((prev) => [...prev, log]),
      (evtError) => setError(evtError.message),
      (latest) => {
        setJob(latest);
        if (latest.status === "failed" && latest.error) {
          setError(latest.error);
        }
      }
    );

    const interval = setInterval(async () => {
      try {
        const latest = await getCreditRatingJob(job.job_id);
        setJob(latest);
        setError((current) => (current && current.toLowerCase().includes("stream") ? null : current));
        if (latest.status === "failed" && latest.error) {
          setError(latest.error);
        }
      } catch (pollError) {
        const message = (pollError as Error).message;
        setError(message);
      }
    }, 1500);

    return () => {
      stopRealtime();
    };
  }, [job?.job_id]);

  const isRunning = useMemo(() => job?.status === "running" || job?.status === "queued", [job?.status]);
  const showEngagementBeam = isRunning || loading;
  const runningFocusText = useMemo(() => {
    if (loading) {
      return "INIT: Preparing your credit rating comparison workspace request...";
    }
    if (!logs.length) {
      return "AnalystIQ is collecting agency signals, validating credit evidence, and constructing the comparison matrix...";
    }
    const latest = logs[logs.length - 1];
    const cleanMessage = latest.message
      .replace(/[\p{Extended_Pictographic}\uFE0F]/gu, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!cleanMessage) {
      return "AnalystIQ is processing your credit rating workspace run.";
    }
    const phaseLabel = latest.phase ? latest.phase.toUpperCase() : "STATUS";
    return `${phaseLabel}: ${cleanMessage}`;
  }, [loading, logs]);

  function toggleAgency(agency: string) {
    setSelectedAgencies((prev) => {
      if (prev.includes(agency)) {
        if (prev.length === 1) return prev;
        return prev.filter((item) => item !== agency);
      }
      return [...prev, agency];
    });
  }

  function handleStartYearChange(value: number) {
    setStartYear(value);
    if (value > endYear) {
      setEndYear(value);
    }
  }

  function handleEndYearChange(value: number) {
    setEndYear(value);
    if (value < startYear) {
      setStartYear(value);
    }
  }

  async function handleGenerate() {
    if (!ticker || selectedAgencies.length === 0 || endYear < startYear) return;
    setLoading(true);
    setError(null);
    setLogs([]);
    try {
      const created = await createCreditRatingJob({
        ticker,
        agencies: selectedAgencies,
        startYear,
        endYear,
      });
      setJob(created);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel() {
    if (!job) return;
    await cancelCreditRatingJob(job.job_id);
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-blue-50 p-6 shadow-panel">
        <div className="mb-4 flex items-center gap-3">
          <span className="rounded-full border border-indigo-200 bg-indigo-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-indigo-700">
            Credit Workspace
          </span>
          <span className="text-sm font-medium text-slate-500">Agency rating comparison</span>
        </div>
        <h2 className="text-3xl font-semibold tracking-tight text-slate-900">Credit Rating Workspace</h2>
        <p className="mt-3 max-w-4xl text-base leading-7 text-slate-600">
          Compare selected agency perspectives side-by-side with evidence-backed synthesis and citation-linked matrix output.
        </p>
      </section>

      {showEngagementBeam ? (
        <section className="overflow-hidden rounded-xl border border-blue-200 bg-blue-50/70 p-3">
          <div className="running-beam h-2 rounded-full" />
          <p className="marquee-text mt-2 text-sm font-medium text-blue-700">{runningFocusText}</p>
        </section>
      ) : null}

      <CreditRatingStatusStrip job={job} />
      {error ? <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

      <div className="grid gap-4 xl:grid-cols-[320px,1fr,360px]">
        <CreditRatingConfigPanel
          options={options}
          ticker={ticker}
          selectedAgencies={selectedAgencies}
          startYear={startYear}
          endYear={endYear}
          isRunning={isRunning || loading}
          onTickerChange={setTicker}
          onToggleAgency={toggleAgency}
          onStartYearChange={handleStartYearChange}
          onEndYearChange={handleEndYearChange}
          onGenerate={handleGenerate}
          onCancel={handleCancel}
        />
        <CreditRatingOutputPanel job={job} isRunning={isRunning || loading} />
        <ActivityTimeline logs={logs} />
      </div>
    </div>
  );
}

