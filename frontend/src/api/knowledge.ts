import {
  API_BASE_URL,
  ApiError,
  requestJson,
} from '@/api/http'
import type {
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
  KnowledgeBaseDeleteResponse,
  KnowledgeBaseListResponse,
  KnowledgeBaseUpdatePayload,
  KnowledgeDocumentDeleteResponse,
  KnowledgeDocumentListResponse,
  KnowledgeDocumentUploadResponse,
} from '@/types/knowledge'

export async function listKnowledgeBases(
  token: string,
): Promise<KnowledgeBaseListResponse> {
  return requestJson<KnowledgeBaseListResponse>(
    '/api/v1/knowledge/bases?limit=100&offset=0',
    {},
    token,
  )
}

export async function createKnowledgeBase(
  payload: KnowledgeBaseCreatePayload,
  token: string,
): Promise<KnowledgeBase> {
  return requestJson<KnowledgeBase>(
    '/api/v1/knowledge/bases',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    token,
  )
}


export async function updateKnowledgeBase(
  knowledgeBaseId: number,
  payload: KnowledgeBaseUpdatePayload,
  token: string,
): Promise<KnowledgeBase> {
  return requestJson<KnowledgeBase>(
    `/api/v1/knowledge/bases/${knowledgeBaseId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    token,
  )
}

export async function deleteKnowledgeBase(
  knowledgeBaseId: number,
  token: string,
): Promise<KnowledgeBaseDeleteResponse> {
  return requestJson<KnowledgeBaseDeleteResponse>(
    `/api/v1/knowledge/bases/${knowledgeBaseId}`,
    {
      method: 'DELETE',
    },
    token,
  )
}

export async function listKnowledgeDocuments(
  knowledgeBaseId: number,
  token: string,
): Promise<KnowledgeDocumentListResponse> {
  return requestJson<KnowledgeDocumentListResponse>(
    `/api/v1/knowledge/documents?knowledge_base_id=${knowledgeBaseId}&limit=100&offset=0`,
    {},
    token,
  )
}

export async function deleteKnowledgeDocument(
  documentId: number,
  token: string,
): Promise<KnowledgeDocumentDeleteResponse> {
  return requestJson<KnowledgeDocumentDeleteResponse>(
    `/api/v1/knowledge/documents/${documentId}`,
    {
      method: 'DELETE',
    },
    token,
  )
}

export async function uploadKnowledgeDocument(
  file: File,
  knowledgeBaseId: number,
  priority: number,
  token: string,
): Promise<KnowledgeDocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('knowledge_base_id', String(knowledgeBaseId))
  form.append('priority', String(priority))

  let response: Response

  try {
    response = await fetch(
      `${API_BASE_URL}/api/v1/knowledge/documents`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: form,
      },
    )
  } catch {
    throw new ApiError(
      0,
      '无法连接后端服务，请确认 FastAPI 已启动',
    )
  }

  const contentType =
    response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractUploadError(payload),
    )
  }

  return payload as KnowledgeDocumentUploadResponse
}

function extractUploadError(payload: unknown): string {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'detail' in payload
  ) {
    const detail = (payload as { detail?: unknown }).detail

    if (typeof detail === 'string') {
      return detail
    }

    if (
      typeof detail === 'object' &&
      detail !== null &&
      'message' in detail &&
      typeof (detail as { message?: unknown }).message ===
        'string'
    ) {
      return (detail as { message: string }).message
    }

    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0]
      if (
        typeof first === 'object' &&
        first !== null &&
        'msg' in first &&
        typeof (first as { msg?: unknown }).msg === 'string'
      ) {
        return (first as { msg: string }).msg
      }
    }
  }

  return '文档上传失败，请稍后重试'
}
