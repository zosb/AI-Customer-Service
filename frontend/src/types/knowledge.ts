export interface KnowledgeBase {
  id: number
  name: string
  description: string | null
  routing_description: string | null
  is_active: boolean
  created_by: number | null
  document_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseListResponse {
  items: KnowledgeBase[]
  total: number
  limit: number
  offset: number
}

export interface KnowledgeBaseCreatePayload {
  name: string
  description?: string | null
  routing_description?: string | null
}

export interface KnowledgeBaseUpdatePayload {
  name?: string
  description?: string | null
  routing_description?: string | null
  is_active?: boolean
}

export interface KnowledgeBaseDeleteResponse {
  knowledge_base_id: number
  deleted: boolean
  document_count: number
  chunk_count: number
  vector_count: number
  disk_files_removed: boolean
  disk_cleanup_failures: string[]
}

export type KnowledgeDocumentStatus =
  | 'processing'
  | 'ready'
  | 'failed'

export interface KnowledgeDocument {
  id: number
  knowledge_base_id: number
  original_name: string
  file_extension: string
  mime_type: string | null
  file_size_bytes: number
  status: KnowledgeDocumentStatus
  error_message: string | null
  chunk_count: number
  content_version: number
  uploaded_by: number | null
  processed_at: string | null
  created_at: string
  updated_at: string
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocument[]
  total: number
  limit: number
  offset: number
}

export interface KnowledgeDocumentUploadResponse {
  document: KnowledgeDocument
  embedding_dimension: number
  sha256: string
}

export interface KnowledgeDocumentDeleteResponse {
  document_id: number
  deleted: boolean
  vector_data_deleted: boolean
  disk_file_removed: boolean
}
