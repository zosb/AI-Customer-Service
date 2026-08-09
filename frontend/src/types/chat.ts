export type ChatSessionStatus = 'active' | 'archived'
export type ChatRole = 'user' | 'assistant' | 'system'
export type RetrievalStatus = 'matched' | 'empty' | 'skipped' | 'failed'

export interface ChatSession {
  id: number
  user_id: number
  title: string
  status: ChatSessionStatus
  selected_knowledge_base_id: number | null
  last_message_at: string | null
  created_at: string
  updated_at: string
}

export interface ChatSessionListResponse {
  items: ChatSession[]
  total: number
  limit: number
  offset: number
}

export interface ChatMessage {
  id: number
  session_id: number
  user_id: number | null
  reply_to_message_id: number | null
  role: ChatRole
  content: string
  intent: string | null
  routed_knowledge_base_id: number | null
  retrieval_status: RetrievalStatus | null
  is_fallback: boolean
  question_char_count: number | null
  prompt_token_estimate: number | null
  completion_token_count: number | null
  follow_up_suggestions: string[] | null
  stream_completed_at: string | null
  created_at: string
  updated_at: string
}

export interface ChatMessageHistoryResponse {
  session: ChatSession
  messages: ChatMessage[]
}

export interface MessageSource {
  id: number
  message_id: number
  document_id: number | null
  chunk_id: number | null
  document_name: string
  chunk_summary: string
  distance: number | null
  similarity_score: number | null
  rank: number
  created_at: string
}

export interface ChatStreamMeta {
  session_id: number
  user_message_id: number
  intent: string
  daily_question_count: number
  retrieval_status: string
  routed_knowledge_base_id: number | null
  route_mode: 'auto' | 'manual' | 'none'
  route_score: number | null
}

export interface ChatStreamDone {
  assistant_message_id: number
  content: string
  is_fallback: boolean
  retrieval_status: RetrievalStatus
  follow_up_suggestions: string[]
  source_count: number
  routed_knowledge_base_id: number | null
  route_mode: 'auto' | 'manual' | 'none'
  route_score: number | null
}

export type ChatStreamEvent =
  | { event: 'meta'; data: ChatStreamMeta }
  | { event: 'delta'; data: { content: string } }
  | { event: 'replace'; data: { content: string } }
  | { event: 'sources'; data: { items: MessageSource[] } }
  | { event: 'done'; data: ChatStreamDone }
  | { event: 'error'; data: { code: string; message: string } }


export type FeedbackRating = 1 | -1

export interface MessageFeedback {
  id: number
  message_id: number
  user_id: number
  rating: FeedbackRating
  comment: string | null
  created_at: string
  updated_at: string
}

export interface MessageFeedbackDeleteResponse {
  message_id: number
  status: 'deleted' | 'not_found'
}
