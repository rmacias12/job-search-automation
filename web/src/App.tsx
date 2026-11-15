import { useState, useCallback } from "react"
import { useJobs } from "@/hooks/useJobs"
import { JobList } from "@/components/JobList"
import { StatsPanel } from "@/components/StatsPanel"
import { StatusFilter } from "@/components/StatusFilter"
import { SearchFilter } from "@/components/SearchFilter"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"
import { JobStatus, SortKey, SORT_OPTIONS } from "@/types/job"
import { ThemeProvider } from "@/components/ThemeProvider"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Button } from "@/components/ui/button"
import { RefreshCw, AlertCircle, Briefcase, Search, Trash2 } from "lucide-react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

function AppContent() {
  const { 
    jobs, 
    stats, 
    loading, 
    error, 
    statusFilter, 
    setStatusFilter,
    minScore,
    setMinScore,
    maxScore,
    setMaxScore,
    updateStatus,
    deleteJob,
    bulkDeleteJobs,
    refresh,
    searchQuery,
    setSearchQuery,
    sortBy,
    setSortBy,
    total,
    hasMore,
    loadMore,
  } = useJobs()

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [isBulkDeleteOpen, setIsBulkDeleteOpen] = useState(false)

  const handleStatusChange = useCallback(async (id: number, status: string) => {
    await updateStatus(id, status)
  }, [updateStatus])

  const handleDelete = useCallback(async (id: number) => {
    await deleteJob(id)
  }, [deleteJob])

  const handleBulkDelete = async (ids: number[]) => {
    await bulkDeleteJobs(ids)
    setSelectedIds(new Set()) // Clear selection after delete
  }

  const handleSelect = useCallback((id: number, selected: boolean) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev)
      if (selected) {
        newSet.add(id)
      } else {
        newSet.delete(id)
      }
      return newSet
    })
  }, [])

  const handleSelectAll = () => {
    if (selectedIds.size === jobs.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(jobs.map(job => job.match_id)))
    }
  }

  // Clear selection when filters change
  const toggleStatusFilter = useCallback((status: JobStatus) => {
    setStatusFilter(prev => prev.includes(status)
      ? prev.filter(s => s !== status)
      : [...prev, status])
    setSelectedIds(new Set())
  }, [setStatusFilter])

  const clearStatusFilter = useCallback(() => {
    setStatusFilter([])
    setSelectedIds(new Set())
  }, [setStatusFilter])

  const handleMinScoreChange = (value: number) => {
    // Ensure min doesn't exceed max
    const newMin = Math.min(value, maxScore)
    setMinScore(newMin)
    setSelectedIds(new Set())
  }

  const handleMaxScoreChange = (value: number) => {
    // Ensure max doesn't go below min
    const newMax = Math.max(value, minScore)
    setMaxScore(newMax)
    setSelectedIds(new Set())
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card sticky top-0 z-40">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {/* Logo Icon */}
              <div className="relative w-10 h-10 flex items-center justify-center bg-primary/10 rounded-lg">
                <Briefcase className="w-5 h-5 text-primary" />
                <div className="absolute -bottom-1 -right-1 w-5 h-5 bg-background rounded-full flex items-center justify-center">
                  <Search className="w-3.5 h-3.5 text-primary" />
                </div>
              </div>
              <div>
                <h1 className="text-2xl font-bold">Job Search Automation</h1>
                <p className="text-sm text-muted-foreground">
                  Manage your job applications
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <Button 
                variant="outline" 
                size="icon"
                onClick={refresh}
                disabled={loading}
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        {error && (
          <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 rounded-lg flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Error loading data</p>
              <p className="text-sm text-destructive/80">{error}</p>
              <p className="text-sm text-muted-foreground mt-1">
                Make sure the API server is running on port 8000, or create a jobs.json file in the public folder.
              </p>
            </div>
          </div>
        )}

        {/* Stats Panel */}
        <StatsPanel 
          stats={stats} 
          onStatusFilter={toggleStatusFilter}
          onClearFilter={clearStatusFilter}
          activeFilter={statusFilter}
        />

        {/* Sticky Toolbar - Contains All Filters, Search, Sort, Select All */}
        <div className="sticky top-[73px] z-30 mb-6 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-y py-4 space-y-4">
          {/* Row 1: Status Filter, Min Score, Sort */}
          <div className="flex items-center gap-4 flex-wrap">
            {/* Status Filter */}
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Filter by:</span>
              <StatusFilter 
                value={statusFilter} 
                onChange={(next) => { setStatusFilter(next); setSelectedIds(new Set()) }}
                stats={stats}
              />
            </div>
            
            {/* Score Range Slider */}
            <div className="flex items-center gap-2 flex-1 min-w-[280px] max-w-[380px]">
              <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Score:</span>
              <div className="flex-1 flex flex-col gap-1">
                {/* Track Background */}
                <div className="relative h-6 flex items-center">
                  {/* Gray track background */}
                  <div className="absolute w-full h-2 bg-muted rounded-full"></div>
                  {/* Filled track between sliders */}
                  <div 
                    className="absolute h-2 bg-primary rounded-full"
                    style={{
                      left: `${minScore}%`,
                      width: `${maxScore - minScore}%`
                    }}
                  ></div>
                  {/* Min slider */}
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={minScore}
                    onChange={(e) => handleMinScoreChange(parseInt(e.target.value))}
                    className="absolute w-full h-2 opacity-0 cursor-pointer z-10"
                  />
                  {/* Max slider */}
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={maxScore}
                    onChange={(e) => handleMaxScoreChange(parseInt(e.target.value))}
                    className="absolute w-full h-2 opacity-0 cursor-pointer z-10"
                  />
                  {/* Visual thumbs */}
                  <div 
                    className="absolute w-4 h-4 bg-primary border-2 border-background rounded-full shadow-md pointer-events-none"
                    style={{ left: `calc(${minScore}% - 8px)` }}
                  ></div>
                  <div 
                    className="absolute w-4 h-4 bg-primary border-2 border-background rounded-full shadow-md pointer-events-none"
                    style={{ left: `calc(${maxScore}% - 8px)` }}
                  ></div>
                </div>
                {/* Labels */}
                <div className="flex justify-between text-xs text-muted-foreground px-1">
                  <span>{minScore}%</span>
                  <span>{maxScore}%</span>
                </div>
              </div>
            </div>

            {/* Sort: primary key + tiebreak key */}
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Sort by:</span>
              <Select
                value={sortBy[0]}
                onValueChange={(v) => setSortBy([v as SortKey, ...(sortBy[1] && sortBy[1] !== v ? [sortBy[1]] : [])])}
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SORT_OPTIONS.map(o => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">then:</span>
              <Select
                value={sortBy[1] ?? "none"}
                onValueChange={(v) => setSortBy(v === "none" ? [sortBy[0]] : [sortBy[0], v as SortKey])}
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {SORT_OPTIONS.filter(o => o.value !== sortBy[0]).map(o => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Row 2: Search, Select All, Bulk Delete */}
          <div className="flex items-center gap-4 flex-wrap">
            {/* Search */}
            <div className="flex-1 min-w-[250px] max-w-md">
              <SearchFilter
                value={searchQuery}
                onChange={setSearchQuery}
                placeholder="Search by title, company, or location..."
              />
            </div>

            {/* Select All & Bulk Actions */}
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={jobs.length > 0 && selectedIds.size === jobs.length}
                  onChange={handleSelectAll}
                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                />
                <span className="text-sm font-medium">
                  {selectedIds.size === 0 
                    ? 'Select All' 
                    : selectedIds.size === jobs.length 
                      ? 'Deselect All' 
                      : `Selected ${selectedIds.size}`}
                </span>
              </label>
              
              {selectedIds.size > 0 && (
                <Button 
                  variant="destructive" 
                  size="sm"
                  onClick={() => setIsBulkDeleteOpen(true)}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Blacklist {selectedIds.size}
                </Button>
              )}
            </div>

            {/* Clear All Filters */}
            {(statusFilter.length > 0 || minScore > 0 || maxScore < 100 || searchQuery) && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setStatusFilter([])
                  setMinScore(0)
                  setMaxScore(100)
                  setSearchQuery("")
                  setSelectedIds(new Set())
                }}
              >
                Clear All
              </Button>
            )}
          </div>

          {/* Results Count */}
          {!loading && jobs.length > 0 && (
            <div className="text-sm text-muted-foreground pt-2 border-t">
              <span>Showing {jobs.length} of {total} jobs</span>
              {searchQuery && ` matching "${searchQuery}"`}
              {(minScore > 0 || maxScore < 100) && ` with score ${minScore}% - ${maxScore}%`}
            </div>
          )}
        </div>

        {/* Job List (Scrollable Content Below Toolbar) */}
        {loading && jobs.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-lg text-muted-foreground mb-2">No jobs found</p>
            {(statusFilter.length > 0 || minScore > 0 || searchQuery) && (
              <>
                <button
                  onClick={() => {
                    setStatusFilter([])
                    setMinScore(0)
                    setMaxScore(100)
                    setSearchQuery("")
                  }}
                  className="text-sm text-primary hover:underline"
                >
                  Clear all filters
                </button>
              </>
            )}
          </div>
        ) : (
          <>
            <JobList 
              jobs={jobs}
              selectedIds={selectedIds}
              onStatusChange={handleStatusChange}
              onDelete={handleDelete}
              onSelect={handleSelect}
            />
            {hasMore && (
              <div className="flex justify-center pt-6">
                <Button variant="outline" onClick={loadMore} disabled={loading}>
                  Load more ({total - jobs.length} remaining)
                </Button>
              </div>
            )}
          </>
        )}

        {/* Bulk Delete Confirmation Dialog */}
        <DeleteConfirmDialog
          isOpen={isBulkDeleteOpen}
          onClose={() => setIsBulkDeleteOpen(false)}
          onConfirm={() => {
            handleBulkDelete(Array.from(selectedIds))
            setIsBulkDeleteOpen(false)
          }}
          count={selectedIds.size}
        />
      </main>

      {/* Footer */}
      <footer className="border-t mt-12 py-6 bg-card">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>Job Search Automation • Built with React + Vite + shadcn/ui</p>
        </div>
      </footer>
    </div>
  )
}

function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="job-search-theme">
      <AppContent />
    </ThemeProvider>
  )
}

export default App