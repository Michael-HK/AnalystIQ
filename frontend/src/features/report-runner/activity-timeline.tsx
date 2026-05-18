import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { ReportLog } from "@/types/report";

interface Props {
  logs: ReportLog[];
}

export function ActivityTimeline({ logs }: Props) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Activity Timeline</CardTitle>
        <CardDescription>Live execution trace grouped by phases.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[420px] overflow-y-auto pr-1">
          <div className="space-y-3">
            {logs.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
                Start a report to stream execution updates.
              </p>
            ) : null}
            {logs.map((log, index) => (
              <div key={`${log.timestamp}-${index}`} className="rounded-md border border-border bg-slate-50 p-3">
                <div className="mb-1 flex items-center justify-between">
                  <p className="text-xs font-medium uppercase tracking-wide text-blue-700">{log.phase}</p>
                  <p className="text-xs text-muted-foreground">{new Date(log.timestamp).toLocaleTimeString()}</p>
                </div>
                <p className="text-sm text-slate-700">{log.message}</p>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
