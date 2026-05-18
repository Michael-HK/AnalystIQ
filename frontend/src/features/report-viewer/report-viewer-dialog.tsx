import { Dialog, DialogContent } from "@/components/ui/dialog";
import { viewerUrl } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jobId?: string;
}

export function ReportViewerDialog({ open, onOpenChange, jobId }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[90vh] max-w-[96vw] p-2">
        {jobId ? (
          <iframe
            src={viewerUrl(jobId)}
            title="AnalystIQ report viewer"
            className="h-full w-full rounded-md border border-border bg-white"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Report viewer is available after report generation.
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
