import { Stats, statusDisplayMap, JobStatus } from "@/types/job"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface StatsPanelProps {
  stats: Stats | null
  onStatusFilter: (status: JobStatus) => void
  onClearFilter: () => void
  activeFilter: JobStatus[]
}

export function StatsPanel({ stats, onStatusFilter, onClearFilter, activeFilter }: StatsPanelProps) {
  if (!stats) return null

  const statusOrder: JobStatus[] = [
    'new', 'interested', 'applied', 'phone_screen', 
    'technical_interview', 'final_interview', 'offer', 'rejected', 'withdrawn',
    'not_interested'
  ]

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Pipeline Statistics</span>
          <span className="text-sm font-normal text-muted-foreground">
            {stats.total_matches} total jobs
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between text-sm">
            <span>Response Rate</span>
            <span className="font-medium">{stats.response_rate.toFixed(1)}%</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div 
              className="h-full bg-primary transition-all"
              style={{ width: `${stats.response_rate}%` }}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 pt-2">
            {statusOrder.map((status) => {
              const count = stats[status] || 0
              const percentage = stats.total_matches > 0 
                ? (count / stats.total_matches) * 100 
                : 0
              const isActive = activeFilter.includes(status)

              return (
                <button
                  key={status}
                  onClick={() => onStatusFilter(status)}
                  className={`p-3 rounded-lg border text-left transition-all hover:border-primary ${
                    isActive ? 'border-primary bg-primary/5' : 'border-muted'
                  }`}
                >
                  <div className="text-2xl font-bold">{count}</div>
                  <div className="text-xs text-muted-foreground">
                    {statusDisplayMap[status].label.split(' ').slice(1).join(' ')}
                  </div>
                  <div className="mt-1 h-1 bg-muted rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-primary/50"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </button>
              )
            })}
            
            {/* Blacklisted count */}
            {stats.blacklisted > 0 && (
              <div className="p-3 rounded-lg border border-muted bg-muted/30">
                <div className="text-2xl font-bold text-muted-foreground">{stats.blacklisted}</div>
                <div className="text-xs text-muted-foreground">
                  🚫 Blacklisted
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Won't reappear
                </div>
              </div>
            )}
          </div>

          {activeFilter.length > 0 && (
            <div className="flex justify-center pt-2">
              <button
                onClick={onClearFilter}
                className="text-sm text-muted-foreground hover:text-primary underline"
              >
                Clear filter
              </button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}