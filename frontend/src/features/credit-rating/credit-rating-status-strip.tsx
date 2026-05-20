import { Activity, Building2, CalendarRange, Gauge, Scale } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatCreditPeriodLabel, type CreditRatingJob } from "@/types/credit-rating";

interface Props {
  job: CreditRatingJob | null;
}

function statusVariant(status: string): "default" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "running" || status === "queued") return "warning";
  return "default";
}

export function CreditRatingStatusStrip({ job }: Props) {
  const periodLabel =
    job?.period_label ??
    (job?.start_year && job?.end_year
      ? formatCreditPeriodLabel(job.start_year, job.end_year)
      : "—");

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <div className="rounded-lg bg-blue-100 p-2 text-blue-700">
            <Building2 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Ticker</p>
            <p className="text-base font-semibold">{job?.ticker ?? "—"}</p>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <div className="rounded-lg bg-indigo-100 p-2 text-indigo-700">
            <Scale className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Company</p>
            <p className="text-base font-semibold">{job?.company_name || "Pending inference"}</p>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <div className="rounded-lg bg-amber-100 p-2 text-amber-700">
            <CalendarRange className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Rating period</p>
            <p className="text-base font-semibold">{periodLabel}</p>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-2 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Gauge className="h-5 w-5 text-blue-700" />
              <p className="text-xs text-muted-foreground">Progress</p>
            </div>
            <p className="text-sm font-semibold">{job?.progress ?? 0}%</p>
          </div>
          <Progress value={job?.progress ?? 0} />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2 text-sm">
            <Activity className="h-4 w-4 text-muted-foreground" />
            Status
          </div>
          <Badge variant={statusVariant(job?.status ?? "queued")}>{job?.status ?? "idle"}</Badge>
        </CardContent>
      </Card>
    </div>
  );
}
