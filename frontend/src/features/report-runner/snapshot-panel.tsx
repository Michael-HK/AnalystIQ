import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReportJob } from "@/types/report";

type ReferenceLink = NonNullable<ReportJob["reference_links"]>[string];

interface Props {
  job: ReportJob | null;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function citationPreview(link: ReferenceLink): string {
  const title = link.title || link.url;
  const domain = link.domain;
  let preview = domain ? `${title} (${domain})` : title;
  if (preview.length > 220) {
    preview = `${preview.slice(0, 217)}...`;
  }
  return preview;
}

function citationAnchor(num: string, link: ReferenceLink | undefined): string {
  if (!link?.url) {
    return escapeHtml(num);
  }
  const preview = escapeHtml(citationPreview(link));
  const url = escapeHtml(link.url);
  return (
    `<a href="${url}" class="brief-citation-link" data-preview="${preview}" title="${preview}" ` +
    `target="_blank" rel="noopener noreferrer">[${escapeHtml(num)}]</a>`
  );
}

export function SnapshotPanel({ job }: Props) {
  const preview = job?.opening_section_preview?.trim();
  const keyPoints = job?.key_points ?? [];
  const referenceLinks = job?.reference_links ?? {};

  const renderBriefHtml = (content: string) => {
    const escaped = content
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    const withBold = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    const withCitationLinks = withBold.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_match, citationGroup) => {
      const nums = citationGroup.split(",").map((item: string) => item.trim());
      const parts = nums.map((num: string) => citationAnchor(num, referenceLinks[num]));
      return `[${parts.join(", ")}]`;
    });

    return withCitationLinks.replace(/\n/g, "<br/>");
  };

  return (
    <Card className="overflow-visible">
      <CardHeader>
        <CardTitle>Report Snapshot</CardTitle>
        <CardDescription>Executive opening and headline takeaways.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <div className="overflow-visible rounded-md border border-border bg-slate-50 p-4">
          <h4 className="mb-2 text-sm font-semibold text-slate-800">Report Brief</h4>
          {preview ? (
            <div
              className="whitespace-pre-wrap text-sm leading-7 text-slate-700"
              dangerouslySetInnerHTML={{ __html: renderBriefHtml(preview) }}
            />
          ) : (
            <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
              The report brief will appear after report generation reaches synthesis.
            </p>
          )}
        </div>
        <div className="rounded-md border border-border bg-slate-50 p-4">
          <h4 className="mb-2 text-sm font-semibold text-slate-800">Decision Highlights</h4>
          {keyPoints.length === 0 ? (
            <p className="text-sm text-muted-foreground">Five key points will be listed here.</p>
          ) : (
            <ul className="space-y-2 text-sm text-slate-700">
              {keyPoints.map((point, index) => (
                <li key={`${point}-${index}`} className="rounded bg-white p-2">
                  {point}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
