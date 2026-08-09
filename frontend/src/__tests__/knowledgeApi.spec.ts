import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeDocument,
  listKnowledgeBases,
  listKnowledgeDocuments,
  updateKnowledgeBase,
  uploadKnowledgeDocument,
} from '@/api/knowledge'

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(
  payload: unknown,
  status = 200,
): Response {
  return new Response(
    JSON.stringify(payload),
    {
      status,
      headers: {
        'Content-Type': 'application/json',
      },
    },
  )
}

describe('knowledge API', () => {
  it('loads knowledge bases', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: 7,
            name: '退款政策',
            document_count: 1,
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    )

    const result = await listKnowledgeBases('token')

    expect(result.total).toBe(1)
    expect(result.items[0]?.name).toBe('退款政策')
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/knowledge/bases'),
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    )
  })

  it('creates a knowledge base', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        {
          id: 8,
          name: '物流政策',
          description: null,
          routing_description: '物流',
          is_active: true,
          created_by: 1,
          document_count: 0,
          created_at: '2026-08-07T09:00:00',
          updated_at: '2026-08-07T09:00:00',
        },
        201,
      ),
    )

    const result = await createKnowledgeBase(
      {
        name: '物流政策',
        routing_description: '物流',
      },
      'token',
    )

    expect(result.id).toBe(8)
  })

  it('loads documents for a selected base', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        items: [],
        total: 0,
        limit: 100,
        offset: 0,
      }),
    )

    await listKnowledgeDocuments(7, 'token')

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining(
        'knowledge_base_id=7',
      ),
      expect.any(Object),
    )
  })

  it('uploads multipart without forcing json content type', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        {
          document: {
            id: 11,
            knowledge_base_id: 7,
            original_name: '退款政策.txt',
            file_extension: '.txt',
            mime_type: 'text/plain',
            file_size_bytes: 100,
            status: 'ready',
            error_message: null,
            chunk_count: 1,
            content_version: 1,
            uploaded_by: 1,
            processed_at: '2026-08-07T09:00:00',
            created_at: '2026-08-07T09:00:00',
            updated_at: '2026-08-07T09:00:00',
          },
          embedding_dimension: 1024,
          sha256: 'a'.repeat(64),
        },
        201,
      ),
    )

    const file = new File(
      ['退款政策'],
      '退款政策.txt',
      { type: 'text/plain' },
    )

    const result = await uploadKnowledgeDocument(
      file,
      7,
      10,
      'token',
    )

    expect(result.embedding_dimension).toBe(1024)

    const options = vi.mocked(fetch).mock.calls[0]?.[1]
    expect(options?.body).toBeInstanceOf(FormData)

    const headers = options?.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer token')
    expect('Content-Type' in headers).toBe(false)
  })

  it('deletes a document', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        document_id: 11,
        deleted: true,
        vector_data_deleted: true,
        disk_file_removed: true,
      }),
    )

    const result = await deleteKnowledgeDocument(
      11,
      'token',
    )

    expect(result.vector_data_deleted).toBe(true)
  })
  it('updates a knowledge base with PATCH', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        id: 7,
        name: '退款与售后',
        description: '退款、售后政策',
        routing_description: '退款、到账、退货',
        is_active: false,
        created_by: 1,
        document_count: 2,
        created_at: '2026-08-07T09:00:00',
        updated_at: '2026-08-08T09:00:00',
      }),
    )

    const result = await updateKnowledgeBase(
      7,
      {
        name: '退款与售后',
        is_active: false,
      },
      'token',
    )

    expect(result.is_active).toBe(false)
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/knowledge/bases/7'),
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          name: '退款与售后',
          is_active: false,
        }),
      }),
    )
  })

  it('deletes a knowledge base with lifecycle cleanup summary', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        knowledge_base_id: 7,
        deleted: true,
        document_count: 2,
        chunk_count: 5,
        vector_count: 5,
        disk_files_removed: true,
        disk_cleanup_failures: [],
      }),
    )

    const result = await deleteKnowledgeBase(7, 'token')

    expect(result.deleted).toBe(true)
    expect(result.vector_count).toBe(5)
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/knowledge/bases/7'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

})
