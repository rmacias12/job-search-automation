import { JobStatus, statusDisplayMap } from "@/types/job"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface StatusDropdownProps {
  value: JobStatus
  onChange: (status: JobStatus) => void
}

export function StatusDropdown({ value, onChange }: StatusDropdownProps) {
  return (
    <Select value={value} onValueChange={onChange as (value: string) => void}>
      <SelectTrigger className="w-[180px]">
        <SelectValue>
          <span className="flex items-center gap-2">
            <span>{statusDisplayMap[value].label}</span>
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {Object.entries(statusDisplayMap).map(([status, { label }]) => (
          <SelectItem key={status} value={status}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}