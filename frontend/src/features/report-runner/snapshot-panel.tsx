import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReportJob } from "@/types/report";

interface Props {
  job: ReportJob | null;
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
      const parts = nums.map((num: string) => {
        const link = referenceLinks[num];
        if (!link?.url) return num;
        return `<a href="${link.url}" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline">${num}</a>`;
      });
      return `[${parts.join(", ")}]`;
    });

    return withCitationLinks.replace(/\n/g, "<br/>");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Report Snapshot</CardTitle>
        <CardDescription>Executive opening and headline takeaways.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <div className="rounded-md border border-border bg-slate-50 p-4">
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
