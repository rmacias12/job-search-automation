import { useState, useEffect, useCallback, useRef } from "react"
import { Job, Stats, JobStatus, SortKey } from "@/types/job"

const API_BASE_URL = ""  // same-origin: vite dev server proxies /api to the FastAPI backend
const PAGE_SIZE = 60

export function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<JobStatus[]>([])
  // Default 60+: focus the board on viable matches; the rest is one slider drag away
  const [minScore, setMinScore] = useState<number>(60)
  const [maxScore, setMaxScore] = useState<number>(100)
  const [searchQuery, setSearchQuery] = useState("")
  const [sortBy, setSortBy] = useState<SortKey[]>(["score"])
  const offsetRef = useRef(0)

  const fetchJobs = useCallback(async (reset: boolean) => {
    try {
      setLoading(true)
      setError(null)
      const offset = reset ? 0 : offsetRef.current
      const params = [`limit=${PAGE_SIZE}`, `offset=${offset}`, `sort=${sortBy.join(",")}`]
      if (statusFilter.length) params.push(`status=${statusFilter.join(",")}`)
      if (minScore > 0) params.push(`min_score=${minScore}`)
      if (maxScore < 100) params.push(`max_score=${maxScore}`)
      if (searchQuery) params.push(`q=${encodeURIComponent(searchQuery)}`)

      const response = await fetch(`${API_BASE_URL}/api/jobs?${params.join("&")}`)
      if (!response.ok) throw new Error("Failed to fetch jobs")

      const data = await response.json()
      offsetRef.current = offset + data.jobs.length
      setJobs(reset ? data.jobs : (prev) => [...prev, ...data.jobs])
      setTotal(typeof data.total === "number" ? data.total : data.jobs.length)
      setHasMore(Boolean(data.has_more))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [statusFilter, minScore, maxScore, searchQuery, sortBy])

  // Debounce filter/slider/search changes so dragging doesn't spam the API
  useEffect(() => {
    const t = setTimeout(() => fetchJobs(true), 250)
    return () => clearTimeout(t)
  }, [fetchJobs])

  const loadMore = useCallback(() => fetchJobs(false), [fetchJobs])

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/stats`)
      if (!response.ok) throw new Error("Failed to fetch stats")

      const data = await response.json()
      setStats(data)
    } catch (err) {
      console.error("Failed to fetch stats:", err)
    }
  }, [])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  const updateStatus = useCallback(async (matchId: number, status: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/jobs/${matchId}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      })

      if (!response.ok) throw new Error("Failed to update status")

      // Optimistic local update — no full list refetch. A job whose new status
      // the current view would hide leaves the list immediately.
      const HIDDEN_BY_DEFAULT = ["not_interested", "auto_rejected", "blacklisted"]
      const next = status as JobStatus
      const staysVisible = statusFilter.length
        ? statusFilter.includes(next)
        : !HIDDEN_BY_DEFAULT.includes(next)
      if (staysVisible) {
        setJobs(prev => prev.map(j => j.match_id === matchId ? { ...j, status: next } : j))
      } else {
        setJobs(prev => prev.filter(j => j.match_id !== matchId))
        setTotal(t => Math.max(0, t - 1))
      }
      await fetchStats()

      return true
    } catch (err) {
      console.error("Failed to update status:", err)
      return false
    }
  }, [fetchStats, statusFilter])

  const deleteJob = useCallback(async (matchId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/jobs/${matchId}`, {
        method: "DELETE",
      })

      if (!response.ok) throw new Error("Failed to delete job")

      setJobs(prev => prev.filter(job => job.match_id !== matchId))
      setTotal(t => Math.max(0, t - 1))
      await fetchStats()

      return true
    } catch (err) {
      console.error("Failed to delete job:", err)
      return false
    }
  }, [fetchStats])

  const bulkDeleteJobs = useCallback(async (matchIds: number[]) => {
    try {
      const results = await Promise.all(
        matchIds.map(id =>
          fetch(`${API_BASE_URL}/api/jobs/${id}`, { method: "DELETE" })
        )
      )

      const okIds = matchIds.filter((_, i) => results[i].ok)
      const failed = results.length - okIds.length
      if (failed > 0) {
        console.warn(`${failed} deletions failed`)
      }

      setJobs(prev => prev.filter(job => !okIds.includes(job.match_id)))
      setTotal(t => Math.max(0, t - okIds.length))
      await fetchStats()

      return { success: true, deleted: okIds.length }
    } catch (err) {
      console.error("Failed to bulk delete jobs:", err)
      return { success: false, deleted: 0 }
    }
  }, [fetchStats])

  // Fallback: Load from JSON file if API is not available
  const loadFromFile = useCallback(async () => {
    try {
      const response = await fetch('/jobs.json')
      if (response.ok) {
        const data = await response.json()
        setJobs(data.jobs || [])
        setTotal(data.jobs?.length || 0)
        setHasMore(false)
        setStats(data.stats || null)
      }
    } catch {
      console.log("No local jobs.json found")
    }
  }, [])

  useEffect(() => {
    if (error) {
      loadFromFile()
    }
  }, [error, loadFromFile])

  return {
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
    searchQuery,
    setSearchQuery,
    sortBy,
    setSortBy,
    total,
    hasMore,
    loadMore,
    updateStatus,
    deleteJob,
    bulkDeleteJobs,
    refresh: () => {
      fetchJobs(true)
      fetchStats()
    },
  }
}
