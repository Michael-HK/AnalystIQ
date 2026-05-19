import { useEffect, useState } from "react";
import { Download, Presentation } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { artifactUrl } from "@/lib/api";
import type { ReportJob } from "@/types/report";

interface Props {
  job: ReportJob | null;
  onGeneratePptx: () => void;
  isGeneratingPptx: boolean;
  onOpenViewer: () => void;
}

function downloadHref(job: ReportJob | null, type: "md" | "pdf" | "pptx") {
  if (!job) return undefined;
  return artifactUrl(job.job_id, type);
}

export function ArtifactPanel({ job, onGeneratePptx, isGeneratingPptx, onOpenViewer }: Props) {
  const canGeneratePptx = Boolean(job && job.status === "completed" && job.artifacts.markdown_ready && !isGeneratingPptx);
  const canDownloadPdf = Boolean(job?.artifacts.pdf_ready);
  const canOpenViewer = Boolean(job?.artifacts.markdown_ready);
  const canDownloadPptx = Boolean(job?.artifacts.ppt_ready);
  const [pdfClicked, setPdfClicked] = useState(false);
  const [pptxClicked, setPptxClicked] = useState(false);
  const [viewerClicked, setViewerClicked] = useState(false);

  // Reset click-dismiss only for a new job — not when PPTX becomes ready (avoids re-beaming PDF/viewer).
  useEffect(() => {
    setPdfClicked(false);
    setPptxClicked(false);
    setViewerClicked(false);
  }, [job?.job_id]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Executive Deliverables</CardTitle>
        <CardDescription>Export report artifacts and launch immersive view.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3 xl:grid-cols-3">
        <a href={downloadHref(job, "pdf")} target="_blank" rel="noreferrer">
          <Button
            variant="outline"
            className={`w-full justify-start gap-2 ${canDownloadPdf && !pdfClicked ? "attention-beam" : ""}`}
            disabled={!canDownloadPdf}
            onClick={() => setPdfClicked(true)}
          >
            <Download className="h-4 w-4" />
            Download PDF
          </Button>
        </a>
        <Button
          variant="secondary"
          className="w-full justify-start gap-2"
          onClick={onGeneratePptx}
          disabled={!canGeneratePptx}
        >
          <Presentation className="h-4 w-4" />
          {isGeneratingPptx ? "Generating PPTX..." : "Generate PPTX"}
          <span className="ml-1 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700">
            Beta
          </span>
        </Button>
        <a href={downloadHref(job, "pptx")} target="_blank" rel="noreferrer">
          <Button
            variant="outline"
            className={`w-full justify-start gap-2 ${canDownloadPptx && !pptxClicked ? "attention-beam" : ""}`}
            disabled={!canDownloadPptx}
            onClick={() => setPptxClicked(true)}
          >
            <Download className="h-4 w-4" />
            Download PPTX
          </Button>
        </a>
      </CardContent>
      <CardContent className="flex items-center justify-between pt-0">
        <Badge variant={job?.artifacts.ppt_ready ? "success" : "default"}>
          {job?.artifacts.ppt_ready ? "Deck Ready" : "Deck Pending"}
        </Badge>
        <Button
          variant="ghost"
          onClick={() => {
            setViewerClicked(true);
            onOpenViewer();
          }}
          disabled={!canOpenViewer}
          className={canOpenViewer && !viewerClicked ? "attention-beam" : ""}
        >
          Open Immersive Viewer
        </Button>
      </CardContent>
    </Card>
  );
}
