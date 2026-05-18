import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { ReportJob } from "@/types/report";

interface Props {
  job: ReportJob | null;
}

function renderList(items: string[] | undefined) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-muted-foreground">No data yet.</p>;
  }
  return (
    <ul className="space-y-2 text-sm text-slate-700">
      {items.map((item, index) => (
        <li key={`${item}-${index}`} className="rounded-md bg-slate-50 px-3 py-2">
          {item}
        </li>
      ))}
    </ul>
  );
}

export function ResearchPanels({ job }: Props) {
  const structure = job?.generated_data.structure;
  const webQueries = job?.generated_data.web_queries;
  const financialQueries = job?.generated_data.financial_queries?.map((entry) => `${entry.query} (${entry.ticker})`);
  const hasInvestmentBrief = Boolean(job?.opening_section_preview?.trim());
  const [sectionsOpen, setSectionsOpen] = useState({
    storyline: true,
    market: true,
    financial: true,
  });

  useEffect(() => {
    if (hasInvestmentBrief) {
      setSectionsOpen({ storyline: false, market: false, financial: false });
    }
  }, [hasInvestmentBrief]);

  function toggleSection(section: "storyline" | "market" | "financial") {
    setSectionsOpen((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Research Intelligence</CardTitle>
        <CardDescription>Storyline, market focus, and financial evidence plan.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <section className="space-y-2">
          <button
            type="button"
            className="w-full text-left text-sm font-semibold text-slate-800"
            onClick={() => toggleSection("storyline")}
          >
            Storyline Outline {sectionsOpen.storyline ? "▾" : "▸"}
          </button>
          {sectionsOpen.storyline ? renderList(structure) : null}
        </section>
        <Separator />
        <section className="space-y-2">
          <button
            type="button"
            className="w-full text-left text-sm font-semibold text-slate-800"
            onClick={() => toggleSection("market")}
          >
            Market Research Focus {sectionsOpen.market ? "▾" : "▸"}
          </button>
          {sectionsOpen.market ? renderList(webQueries) : null}
        </section>
        <Separator />
        <section className="space-y-2">
          <button
            type="button"
            className="w-full text-left text-sm font-semibold text-slate-800"
            onClick={() => toggleSection("financial")}
          >
            Financial Analysis Focus {sectionsOpen.financial ? "▾" : "▸"}
          </button>
          {sectionsOpen.financial ? renderList(financialQueries) : null}
        </section>
      </CardContent>
    </Card>
  );
}
