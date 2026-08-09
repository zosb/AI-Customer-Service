export interface AdminOverview {
  total_users: number
  active_users: number
  total_sessions: number
  active_sessions: number
  total_messages: number
  today_questions: number
  total_knowledge_bases: number
  total_documents: number
  feedback_total: number
  positive_feedback: number
  negative_feedback: number
  satisfaction_rate: number
  prompt_token_estimate: number
  completion_token_count: number
}

export interface AdminSession {
  id: number
  user_id: number
  user_label: string
  title: string
  status: 'active' | 'archived'
  selected_knowledge_base_id: number | null
  message_count: number
  last_message_at: string | null
  created_at: string
  updated_at: string
}

export interface AdminSessionListResponse {
  items: AdminSession[]
  total: number
  limit: number
  offset: number
}

export interface AdminMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  intent: string | null
  routed_knowledge_base_id: number | null
  retrieval_status: string | null
  is_fallback: boolean
  feedback_rating: -1 | 1 | null
  feedback_comment: string | null
  created_at: string
}

export interface AdminSessionDetail {
  session: AdminSession
  messages: AdminMessage[]
}

export interface AdminFeedbackIntentStat {
  intent: string
  total: number
  positive: number
  negative: number
  satisfaction_rate: number
}

export interface AdminFeedbackSummary {
  total: number
  positive: number
  negative: number
  satisfaction_rate: number
  by_intent: AdminFeedbackIntentStat[]
}

export interface AdminFeedback {
  id: number
  message_id: number
  session_id: number
  session_title: string
  user_id: number
  user_label: string
  rating: -1 | 1
  comment: string | null
  intent: string | null
  assistant_content: string
  created_at: string
}

export interface AdminFeedbackListResponse {
  items: AdminFeedback[]
  total: number
  limit: number
  offset: number
}

export interface DailyQuestionPoint {
  date: string
  question_count: number
}

export interface DailyQuestionTrend {
  days: number
  total_questions: number
  average_per_day: number
  items: DailyQuestionPoint[]
}
