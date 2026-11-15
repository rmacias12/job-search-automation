import { Job } from "@/types/job"
import { JobCard } from "./JobCard"

interface JobListProps {
  jobs: Job[]
  selectedIds: Set<number>
  onStatusChange: (id: number, status: string) => void
  onDelete?: (id: number) => void
  onSelect: (id: number, selected: boolean) => void
}

// Pure renderer: filtering, searching, sorting and pagination all happen
// server-side in /api/jobs, so this only maps the current page to cards.
export function JobList({ jobs, selectedIds, onStatusChange, onDelete, onSelect }: JobListProps) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {jobs.map((job) => (
          <JobCard
            key={job.match_id}
            job={job}
            onStatusChange={onStatusChange}
            onDelete={onDelete}
            selected={selectedIds.has(job.match_id)}
            onSelect={onSelect}
          />
        ))}
      </div>

      {jobs.length === 0 && (
        <div className="text-center py-12">
          <p className="text-lg text-muted-foreground">No jobs found</p>
        </div>
      )}
    </div>
  )
}
