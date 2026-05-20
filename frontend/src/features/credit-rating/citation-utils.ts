type ReferenceLink = {
  url: string;
  title: string;
  domain: string;
};

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function citationPreview(link: ReferenceLink): string {
  const title = (link.title || link.url || "").trim();
  const domain = (link.domain || "").trim();
  const preview = domain ? `${title} (${domain})` : title;
  return preview.length <= 220 ? preview : `${preview.slice(0, 217)}...`;
}

export function renderTextWithCitations(text: string, referenceLinks: Record<string, ReferenceLink>): string {
  const escaped = escapeHtml(text || "");
  return escaped.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_full, group) => {
    const nums = String(group)
      .split(",")
      .map((item) => item.trim());
    const parts = nums.map((num) => {
      const link = referenceLinks[num];
      if (!link?.url) return num;
      const previewText = escapeHtml(citationPreview(link));
      const url = escapeHtml(link.url);
      return (
        `<a href="${url}" target="_blank" rel="noopener noreferrer" ` +
        `class="brief-citation-link" data-preview="${previewText}">[${num}]</a>`
      );
    });
    return `[${parts.join(", ")}]`;
  });
}

function isSourceDocumentRow(metricCell: string): boolean {
  const normalized = (metricCell || "").trim().toLowerCase();
  return normalized.includes("source document") || normalized === "source";
}

export function parseMarkdownTable(tableMarkdown: string): { headers: string[]; rows: string[][] } {
  const lines = (tableMarkdown || "")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.includes("|"));
  if (lines.length < 2) return { headers: [], rows: [] };

  const parseLine = (line: string) =>
    line
      .split("|")
      .map((cell) => cell.trim())
      .filter((cell) => cell.length > 0);

  const headers = parseLine(lines[0]);
  const bodyLines = lines.slice(1).filter((line) => !/^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(line));
  const rows = bodyLines
    .map(parseLine)
    .filter((row) => row.length > 0)
    .filter((row) => !isSourceDocumentRow(row[0] ?? ""));
  return { headers, rows };
}

