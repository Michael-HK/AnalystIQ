import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { CreditRatingJob } from "@/types/credit-rating";
import { parseMarkdownTable, renderTextWithCitations } from "@/features/credit-rating/citation-utils";
import { creditRatingArtifactUrl } from "@/lib/api";

interface Props {
  job: CreditRatingJob | null;
  isRunning: boolean;
}

export function CreditRatingOutputPanel({ job, isRunning }: Props) {
  const paragraphs = job?.generated_data.comparison_paragraphs ?? [];
  const tableMarkdown = job?.generated_data.comparison_table_markdown ?? "";
  const referenceLinks = job?.reference_links ?? {};
  const parsedTable = parseMarkdownTable(tableMarkdown);
  const [exportType, setExportType] = useState<"doc" | "pdf">("pdf");

  const hasOutput = paragraphs.length > 0 || tableMarkdown.trim().length > 0;
  const isCompleted = job?.status === "completed";
  const canExport = !isRunning && isCompleted && hasOutput;

  const resolvedExportType = useMemo<"doc" | "pdf">(() => {
    if (!job?.artifacts) return exportType;
    if (exportType === "pdf" && job.artifacts.pdf_ready) return "pdf";
    if (exportType === "doc" && job.artifacts.doc_ready) return "doc";
    if (job.artifacts.pdf_ready) return "pdf";
    if (job.artifacts.doc_ready) return "doc";
    return exportType;
  }, [exportType, job?.artifacts]);

  const handleExport = () => {
    if (!canExport || !job?.job_id) return;
    window.open(creditRatingArtifactUrl(job.job_id, resolvedExportType), "_blank", "noopener,noreferrer");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agency Comparison Output</CardTitle>
        <CardDescription>
          Narrative synthesis and a dynamic comparison matrix (Current Rating first, then evidence-driven dimensions) with
          source citations.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <section className="rounded-md border border-border bg-slate-50 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm font-medium text-slate-700">Export format</label>
            <select
              className="h-9 rounded-md border border-input bg-white px-3 text-sm"
              value={exportType}
              onChange={(event) => setExportType(event.target.value as "doc" | "pdf")}
              disabled={isRunning}
            >
              <option value="pdf">PDF</option>
              <option value="doc">Word (.doc)</option>
            </select>
            <Button onClick={handleExport} disabled={!canExport}>
              Export
            </Button>
          </div>
        </section>

        <section className="rounded-md border border-border bg-slate-50 p-4">
          <h4 className="mb-2 text-sm font-semibold text-slate-800">Comparison Narrative</h4>
          {paragraphs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Narrative comparison appears after synthesis completes.</p>
          ) : (
            <div className="space-y-3">
              {paragraphs.map((paragraph, idx) => (
                <p
                  key={`${idx}-${paragraph.slice(0, 20)}`}
                  className="text-sm leading-7 text-slate-700"
                  dangerouslySetInnerHTML={{
                    __html: renderTextWithCitations(paragraph, referenceLinks),
                  }}
                />
              ))}
            </div>
          )}
        </section>

        <section className="rounded-md border border-border bg-slate-50 p-4">
          <h4 className="mb-2 text-sm font-semibold text-slate-800">Comparison Matrix</h4>
          {parsedTable.headers.length === 0 ? (
            <p className="text-sm text-muted-foreground">Matrix table appears after synthesis completes.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    {parsedTable.headers.map((header) => (
                      <th key={header} className="border border-slate-200 bg-white px-3 py-2 text-left font-semibold text-slate-800">
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsedTable.rows.map((row, rowIdx) => (
                    <tr key={`${rowIdx}-${row[0] ?? "row"}`}>
                      {row.map((cell, cellIdx) => (
                        <td
                          key={`${rowIdx}-${cellIdx}`}
                          className="border border-slate-200 bg-white px-3 py-2 align-top text-slate-700"
                          dangerouslySetInnerHTML={{ __html: renderTextWithCitations(cell, referenceLinks) }}
                        />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
