export type JobStatus = 
  | 'new'
  | 'interested'
  | 'applied'
  | 'phone_screen'
  | 'technical_interview'
  | 'final_interview'
  | 'offer'
  | 'rejected'
  | 'withdrawn'
  | 'not_interested';

export interface Job {
  id: number;
  match_id: number;
  title: string;
  company: string;
  location: string;
  url: string;
  match_score: number;
  status: JobStatus;
  notes: string | null;
  salary_min?: number;
  salary_max?: number;
  updated_at: string;
  posted_date?: string | null;
  pulled_at?: string | null;
  remote_status?: string | null;
  salary_is_predicted?: number | null;
  evidence?: string | null;
}

export interface Stats {
  total_matches: number;
  new: number;
  interested: number;
  applied: number;
  phone_screen: number;
  technical_interview: number;
  final_interview: number;
  offer: number;
  rejected: number;
  withdrawn: number;
  not_interested: number;
  auto_rejected: number;
  blacklisted: number;
  response_rate: number;
  avg_match_score: number;
}

export type SortKey = "score" | "pulled" | "posted" | "company" | "salary";

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "score", label: "Match Score" },
  { value: "pulled", label: "Date Pulled" },
  { value: "posted", label: "Date Posted" },
  { value: "company", label: "Company" },
  { value: "salary", label: "Salary" },
];

export const statusDisplayMap: Record<JobStatus, { label: string; color: string; icon: string }> = {
  new: { label: '🆕 New', color: 'bg-gray-100 text-gray-800', icon: 'Circle' },
  interested: { label: '⭐ Interested', color: 'bg-yellow-100 text-yellow-800', icon: 'Star' },
  applied: { label: '✅ Applied', color: 'bg-blue-100 text-blue-800', icon: 'Send' },
  phone_screen: { label: '📞 Phone Screen', color: 'bg-purple-100 text-purple-800', icon: 'Phone' },
  technical_interview: { label: '💻 Technical', color: 'bg-indigo-100 text-indigo-800', icon: 'Code' },
  final_interview: { label: '🎯 Final Round', color: 'bg-pink-100 text-pink-800', icon: 'Target' },
  offer: { label: '🎉 Offer!', color: 'bg-green-100 text-green-800', icon: 'Trophy' },
  rejected: { label: '❌ Rejected', color: 'bg-red-100 text-red-800', icon: 'XCircle' },
  withdrawn: { label: '👋 Withdrawn', color: 'bg-orange-100 text-orange-800', icon: 'LogOut' },
  not_interested: { label: '👎 Not Interested', color: 'bg-gray-200 text-gray-700', icon: 'ThumbsDown' },
};