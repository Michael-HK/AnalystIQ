import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { ReportOptions, ReportType } from "@/types/report";

interface Props {
  options: ReportOptions | null;
  ticker: string;
  reportType: ReportType;
  customInstruction: string;
  presentationStyle: string;
  isRunning: boolean;
  onTickerChange: (value: string) => void;
  onReportTypeChange: (value: ReportType) => void;
  onCustomInstructionChange: (value: string) => void;
  onPresentationStyleChange: (value: string) => void;
  onGenerate: () => void;
  onCancel: () => void;
}

export function ReportConfigPanel(props: Props) {
  const {
    options,
    ticker,
    reportType,
    customInstruction,
    presentationStyle,
    isRunning,
    onTickerChange,
    onReportTypeChange,
    onCustomInstructionChange,
    onPresentationStyleChange,
    onGenerate,
    onCancel,
  } = props;

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Configuration
          <Badge variant={isRunning ? "warning" : "default"}>{isRunning ? "Running" : "Ready"}</Badge>
        </CardTitle>
        <CardDescription>Define ticker, report mode, and executive instruction.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Ticker</label>
          <select
            className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
            value={ticker}
            onChange={(event) => onTickerChange(event.target.value)}
            disabled={!options || isRunning}
          >
            {(options?.tickers ?? []).map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Report Type</label>
          <select
            className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
            value={reportType}
            onChange={(event) => onReportTypeChange(event.target.value as ReportType)}
            disabled={isRunning}
          >
            <option value="investment">Investment Report</option>
            <option value="credit">Credit Analysis Report</option>
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Presentation Style</label>
          <select
            className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
            value={presentationStyle}
            onChange={(event) => onPresentationStyleChange(event.target.value)}
            disabled={!options || isRunning}
          >
            {(options?.presentation_styles ?? []).map((style) => (
              <option key={style} value={style}>
                {style}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">Custom Instruction</label>
          <Textarea
            value={customInstruction}
            onChange={(event) => onCustomInstructionChange(event.target.value)}
            placeholder="Refine tone, emphasize risk posture, or enforce analytical priorities..."
            maxLength={2000}
            disabled={isRunning}
          />
          <p className="text-xs text-muted-foreground">{customInstruction.length}/2000</p>
        </div>

        <div className="flex gap-2 pt-2">
          <Button className="flex-1" onClick={onGenerate} disabled={!options || isRunning}>
            Generate Report
          </Button>
          <Button variant="destructive" onClick={onCancel} disabled={!isRunning}>
            Stop
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
