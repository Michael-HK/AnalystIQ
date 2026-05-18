import { Activity, Building2, FileText, Gauge } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { ReportJob } from "@/types/report";

interface Props {
  job: ReportJob | null;
}

function statusVariant(status: string): "default" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "running" || status === "queued") return "warning";
  return "default";
}

export function StatusStrip({ job }: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
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
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Company</p>
            <p className="text-base font-semibold">{job?.company_name || "Pending inference"}</p>
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
