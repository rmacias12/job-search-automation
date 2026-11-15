"use client"

import { memo, useState } from "react"
import { Job } from "@/types/job"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { StatusDropdown } from "./StatusDropdown"
import { DeleteConfirmDialog } from "./DeleteConfirmDialog"
import { ExternalLink, Building2, MapPin, DollarSign, Trash2 } from "lucide-react"

interface JobCardProps {
  job: Job
  onStatusChange: (id: number, status: string) => void
  onDelete?: (id: number) => void
  selected?: boolean
  onSelect?: (id: number, selected: boolean) => void
}

function JobCardBase({ job, onStatusChange, onDelete, selected, onSelect }: JobCardProps) {
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)

  const formatSalary = (min?: number, max?: number) => {
    const estimated = job.salary_is_predicted === 1 ? " (est.)" : ""
    if (!min && !max) return "Salary not listed"
    if (min && max) return `$${(min/1000).toFixed(0)}k - $${(max/1000).toFixed(0)}k${estimated}`
    if (min) return `$${(min/1000).toFixed(0)}k+${estimated}`
    return `Up to $${(max!/1000).toFixed(0)}k${estimated}`
  }

  const getScoreColor = (score: number) => {
    if (score >= 60) return "bg-green-500"
    if (score >= 40) return "bg-yellow-500"
    return "bg-gray-500"
  }

  const handleConfirmDelete = () => {
    onDelete?.(job.match_id)
    setIsDeleteOpen(false)
  }

  return (
    <Card className={`hover:shadow-lg transition-shadow ${selected ? 'ring-2 ring-primary bg-primary/5' : ''}`}>
      <CardHeader className="pb-3">
        <div className="flex justify-between items-start gap-4">
          <div className="flex items-start gap-3 flex-1">
            {onSelect && (
              <input
                type="checkbox"
                checked={selected}
                onChange={(e) => onSelect(job.match_id, e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
            )}
            <div className="flex-1">
              <CardTitle className="text-lg font-semibold leading-tight mb-1">
                {job.title}
              </CardTitle>
              <div className="flex items-center gap-2 text-muted-foreground">
                <Building2 className="h-4 w-4" />
                <span>{job.company}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className={`h-10 w-10 rounded-full ${getScoreColor(job.match_score)} flex items-center justify-center text-white font-bold text-sm`}>
              {job.match_score.toFixed(0)}%
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
          <div className="flex items-center gap-1">
            <MapPin className="h-4 w-4" />
            <span>{job.location}</span>
          </div>
          {(job.remote_status === "remote" || job.remote_status === "hybrid") && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${job.remote_status === "remote" ? "bg-emerald-100 text-emerald-800" : "bg-sky-100 text-sky-800"}`}>
              {job.remote_status === "remote" ? "🌐 Remote" : "🏠 Hybrid"}
            </span>
          )}
          {(job.salary_min || job.salary_max) && (
            <div className="flex items-center gap-1">
              <DollarSign className="h-4 w-4" />
              <span>{formatSalary(job.salary_min, job.salary_max)}</span>
            </div>
          )}
        </div>

        {job.notes && (
          <p className="text-sm text-muted-foreground italic border-l-2 border-muted pl-3">
            &ldquo;{job.notes.length > 100 ? job.notes.slice(0, 100) + '...' : job.notes}&rdquo;
          </p>
        )}

        <div className="flex items-center justify-between pt-2">
          <StatusDropdown
            value={job.status}
            onChange={(status) => onStatusChange(job.match_id, status)}
          />
          
          <div className="flex gap-2">
            <Button variant="outline" size="sm" asChild>
              <a href={job.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-1" />
                View
              </a>
            </Button>
            {onDelete && (
              <Button 
                variant="ghost" 
                size="sm" 
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                onClick={() => setIsDeleteOpen(true)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        <div className="text-xs text-muted-foreground pt-1">
          Match ID: {job.match_id} • Pulled: {job.pulled_at ? new Date(job.pulled_at).toLocaleDateString() : "—"}
          {job.posted_date ? ` • Posted: ${new Date(job.posted_date).toLocaleDateString()}` : ""}
        </div>
      </CardContent>

      <DeleteConfirmDialog
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        onConfirm={handleConfirmDelete}
        jobTitle={job.title}
        company={job.company}
      />
    </Card>
  )
}

// Stable props (useCallback handlers in App) let unchanged cards skip re-render
export const JobCard = memo(JobCardBase)