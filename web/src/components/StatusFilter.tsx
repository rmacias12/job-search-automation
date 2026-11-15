import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Filter, ChevronDown } from "lucide-react"
import { JobStatus, Stats } from "@/types/job"

interface StatusFilterProps {
  value: JobStatus[]
  onChange: (value: JobStatus[]) => void
  stats: Stats | null
}

const STATUS_OPTIONS: { value: JobStatus; label: string; color: string; countKey: keyof Stats }[] = [
  { value: "new", label: "New", color: "bg-blue-100 text-blue-800", countKey: "new" },
  { value: "interested", label: "Interested", color: "bg-purple-100 text-purple-800", countKey: "interested" },
  { value: "applied", label: "Applied", color: "bg-yellow-100 text-yellow-800", countKey: "applied" },
  { value: "phone_screen", label: "Phone Screen", color: "bg-orange-100 text-orange-800", countKey: "phone_screen" },
  { value: "technical_interview", label: "Technical Interview", color: "bg-pink-100 text-pink-800", countKey: "technical_interview" },
  { value: "final_interview", label: "Final Interview", color: "bg-indigo-100 text-indigo-800", countKey: "final_interview" },
  { value: "offer", label: "Offer", color: "bg-green-100 text-green-800", countKey: "offer" },
  { value: "rejected", label: "Rejected", color: "bg-red-100 text-red-800", countKey: "rejected" },
  { value: "withdrawn", label: "Withdrawn", color: "bg-gray-100 text-gray-600", countKey: "withdrawn" },
  { value: "not_interested", label: "Not Interested", color: "bg-gray-200 text-gray-700", countKey: "not_interested" },
]

export function StatusFilter({ value, onChange, stats }: StatusFilterProps) {
  const toggle = (s: JobStatus) =>
    onChange(value.includes(s) ? value.filter(v => v !== s) : [...value, s])

  const getCount = (key: keyof Stats): number => (stats?.[key] as number) || 0

  const single = value.length === 1 ? STATUS_OPTIONS.find(o => o.value === value[0]) : undefined
  const label = value.length === 0
    ? "All Statuses"
    : single
      ? single.label
      : `${value.length} statuses`
  const shownCount = value.length === 0
    ? (stats?.total_matches ?? 0)
    : value.reduce((sum, s) => sum + getCount(s), 0)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="min-w-[200px] justify-between gap-2">
          <span className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Badge variant="secondary" className={single ? single.color : "bg-gray-100 text-gray-800"}>
              {label}
            </Badge>
          </span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            ({shownCount})
            <ChevronDown className="h-4 w-4" />
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[240px]">
        <DropdownMenuLabel>Filter by status (multi-select)</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {STATUS_OPTIONS.map(option => (
          <DropdownMenuCheckboxItem
            key={option.value}
            checked={value.includes(option.value)}
            onCheckedChange={() => toggle(option.value)}
          >
            <span className="flex items-center justify-between w-full gap-4">
              <Badge variant="secondary" className={option.color}>{option.label}</Badge>
              <span className="text-xs text-muted-foreground">{getCount(option.countKey)}</span>
            </span>
          </DropdownMenuCheckboxItem>
        ))}
        {value.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => onChange([])}>Clear selection</DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
