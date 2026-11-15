import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Trash2, AlertTriangle } from "lucide-react"

interface DeleteConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  jobTitle?: string
  company?: string
  count?: number
}

export function DeleteConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  jobTitle,
  company,
  count = 1,
}: DeleteConfirmDialogProps) {
  const isBulk = count > 1

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            {isBulk ? `Blacklist ${count} jobs?` : "Blacklist this job?"}
          </DialogTitle>
          <DialogDescription asChild>
            <div className="pt-4 space-y-2">
              <span>
                {isBulk 
                  ? `You are about to permanently blacklist ${count} selected jobs.`
                  : <>You are about to permanently blacklist:<br />
                     <span className="font-semibold text-foreground">"{jobTitle}"</span> at <span className="font-semibold text-foreground">{company}</span></>
                }
              </span>
              <div className="flex items-start gap-2 p-3 bg-muted rounded-md mt-2">
                <Trash2 className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                <span className="text-sm text-muted-foreground">
                  Blacklisted jobs will be hidden and won't reappear in future searches. 
                  This action cannot be undone.
                </span>
              </div>
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button 
            variant="destructive" 
            onClick={onConfirm}
            className="gap-2"
          >
            <Trash2 className="h-4 w-4" />
            {isBulk ? `Blacklist ${count}` : "Blacklist"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}