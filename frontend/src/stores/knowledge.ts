import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createKnowledgeBase as createKnowledgeBaseApi,
  deleteKnowledgeBase as deleteKnowledgeBaseApi,
  deleteKnowledgeDocument as deleteKnowledgeDocumentApi,
  listKnowledgeBases,
  listKnowledgeDocuments,
  updateKnowledgeBase as updateKnowledgeBaseApi,
  uploadKnowledgeDocument as uploadKnowledgeDocumentApi,
} from '@/api/knowledge'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type {
  KnowledgeBase,
  KnowledgeBaseCreatePayload,
  KnowledgeBaseUpdatePayload,
  KnowledgeDocument,
} from '@/types/knowledge'

export const useKnowledgeStore = defineStore(
  'knowledge',
  () => {
    const auth = useAuthStore()

    const bases = ref<KnowledgeBase[]>([])
    const selectedBaseId = ref<number | null>(null)
    const documents = ref<KnowledgeDocument[]>([])
    const loadingBases = ref(false)
    const loadingDocuments = ref(false)
    const creating = ref(false)
    const uploading = ref(false)
    const deletingDocumentId = ref<number | null>(null)
    const updatingBaseId = ref<number | null>(null)
    const deletingBaseId = ref<number | null>(null)

    const selectedBase = computed(
      () =>
        bases.value.find(
          (item) => item.id === selectedBaseId.value,
        ) ?? null,
    )

    function requireToken(): string {
      if (!auth.token) {
        throw new ApiError(
          401,
          '登录状态已失效，请重新登录',
        )
      }
      return auth.token
    }

    async function loadBases(): Promise<void> {
      loadingBases.value = true
      try {
        const result = await listKnowledgeBases(
          requireToken(),
        )
        bases.value = result.items

        if (
          selectedBaseId.value === null ||
          !bases.value.some(
            (item) => item.id === selectedBaseId.value,
          )
        ) {
          selectedBaseId.value =
            bases.value[0]?.id ?? null
        }
      } finally {
        loadingBases.value = false
      }
    }

    async function selectBase(
      knowledgeBaseId: number,
    ): Promise<void> {
      selectedBaseId.value = knowledgeBaseId
      await loadDocuments()
    }

    async function loadDocuments(): Promise<void> {
      if (selectedBaseId.value === null) {
        documents.value = []
        return
      }

      loadingDocuments.value = true
      try {
        const result = await listKnowledgeDocuments(
          selectedBaseId.value,
          requireToken(),
        )
        documents.value = result.items
      } finally {
        loadingDocuments.value = false
      }
    }

    async function initialize(): Promise<void> {
      await loadBases()
      await loadDocuments()
    }

    async function createBase(
      payload: KnowledgeBaseCreatePayload,
    ): Promise<KnowledgeBase> {
      creating.value = true
      try {
        const created = await createKnowledgeBaseApi(
          payload,
          requireToken(),
        )
        bases.value = [created, ...bases.value]
        selectedBaseId.value = created.id
        documents.value = []
        return created
      } finally {
        creating.value = false
      }
    }

    async function updateBase(
      knowledgeBaseId: number,
      payload: KnowledgeBaseUpdatePayload,
    ): Promise<KnowledgeBase> {
      updatingBaseId.value = knowledgeBaseId
      try {
        const updated = await updateKnowledgeBaseApi(
          knowledgeBaseId,
          payload,
          requireToken(),
        )
        bases.value = bases.value.map((item) =>
          item.id === knowledgeBaseId ? updated : item,
        )
        return updated
      } finally {
        updatingBaseId.value = null
      }
    }

    async function setBaseActive(
      knowledgeBaseId: number,
      isActive: boolean,
    ): Promise<KnowledgeBase> {
      return updateBase(knowledgeBaseId, {
        is_active: isActive,
      })
    }

    async function deleteBase(
      knowledgeBaseId: number,
    ): Promise<void> {
      deletingBaseId.value = knowledgeBaseId
      try {
        await deleteKnowledgeBaseApi(
          knowledgeBaseId,
          requireToken(),
        )

        const deletingSelected =
          selectedBaseId.value === knowledgeBaseId
        bases.value = bases.value.filter(
          (item) => item.id !== knowledgeBaseId,
        )

        if (deletingSelected) {
          selectedBaseId.value = bases.value[0]?.id ?? null
          await loadDocuments()
        }
      } finally {
        deletingBaseId.value = null
      }
    }

    async function uploadDocument(
      file: File,
      priority = 0,
    ): Promise<void> {
      if (selectedBaseId.value === null) {
        throw new ApiError(
          422,
          '请先选择或创建知识库',
        )
      }

      uploading.value = true
      try {
        await uploadKnowledgeDocumentApi(
          file,
          selectedBaseId.value,
          priority,
          requireToken(),
        )
        await Promise.all([
          loadDocuments(),
          loadBases(),
        ])
      } finally {
        uploading.value = false
      }
    }

    async function deleteDocument(
      documentId: number,
    ): Promise<void> {
      deletingDocumentId.value = documentId
      try {
        await deleteKnowledgeDocumentApi(
          documentId,
          requireToken(),
        )
        documents.value = documents.value.filter(
          (item) => item.id !== documentId,
        )
        await loadBases()
      } finally {
        deletingDocumentId.value = null
      }
    }

    function reset(): void {
      bases.value = []
      selectedBaseId.value = null
      documents.value = []
      loadingBases.value = false
      loadingDocuments.value = false
      creating.value = false
      uploading.value = false
      deletingDocumentId.value = null
      updatingBaseId.value = null
      deletingBaseId.value = null
    }

    return {
      bases,
      selectedBaseId,
      selectedBase,
      documents,
      loadingBases,
      loadingDocuments,
      creating,
      uploading,
      deletingDocumentId,
      updatingBaseId,
      deletingBaseId,
      initialize,
      loadBases,
      selectBase,
      loadDocuments,
      createBase,
      updateBase,
      setBaseActive,
      deleteBase,
      uploadDocument,
      deleteDocument,
      reset,
    }
  },
)
