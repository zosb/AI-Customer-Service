<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useKnowledgeStore } from '@/stores/knowledge'
import type { KnowledgeBase } from '@/types/knowledge'
import { relativeApiTime } from '@/utils/datetime'

const router = useRouter()
const auth = useAuthStore()
const knowledge = useKnowledgeStore()

const pageError = ref('')
const showCreateForm = ref(false)
const name = ref('')
const description = ref('')
const routingDescription = ref('')
const priority = ref(0)
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const openMenuBaseId = ref<number | null>(null)
const editingBaseId = ref<number | null>(null)
const editName = ref('')
const editDescription = ref('')
const editRoutingDescription = ref('')


const accountLabel = computed(
  () =>
    auth.user?.display_name ||
    auth.user?.email ||
    auth.user?.phone ||
    '用户',
)

onMounted(async () => {
  await runSafely(async () => {
    await knowledge.initialize()
  })
})

async function runSafely(
  action: () => Promise<void>,
): Promise<void> {
  pageError.value = ''

  try {
    await action()
  } catch (error) {
    if (error instanceof ApiError) {
      pageError.value = error.detail
      if (error.status === 401) {
        logout()
      }
      return
    }

    pageError.value = '操作失败，请稍后重试'
  }
}

async function createBase(): Promise<void> {
  await runSafely(async () => {
    const trimmedName = name.value.trim()
    if (!trimmedName) {
      throw new ApiError(422, '请输入知识库名称')
    }

    await knowledge.createBase({
      name: trimmedName,
      description: description.value.trim() || null,
      routing_description:
        routingDescription.value.trim() || null,
    })

    name.value = ''
    description.value = ''
    routingDescription.value = ''
    showCreateForm.value = false
  })
}

async function chooseBase(
  knowledgeBaseId: number,
): Promise<void> {
  await runSafely(async () => {
    await knowledge.selectBase(knowledgeBaseId)
  })
}

function toggleBaseMenu(knowledgeBaseId: number): void {
  openMenuBaseId.value =
    openMenuBaseId.value === knowledgeBaseId
      ? null
      : knowledgeBaseId
}

function closeBaseMenu(): void {
  openMenuBaseId.value = null
}

function startEditBase(base: KnowledgeBase): void {
  closeBaseMenu()
  editingBaseId.value = base.id
  editName.value = base.name
  editDescription.value = base.description ?? ''
  editRoutingDescription.value =
    base.routing_description ?? ''
}

function cancelEditBase(): void {
  editingBaseId.value = null
  editName.value = ''
  editDescription.value = ''
  editRoutingDescription.value = ''
}

async function saveEditBase(): Promise<void> {
  const knowledgeBaseId = editingBaseId.value
  if (knowledgeBaseId === null) {
    return
  }

  const trimmedName = editName.value.trim()
  if (!trimmedName) {
    pageError.value = '知识库名称不能为空'
    return
  }

  await runSafely(async () => {
    await knowledge.updateBase(knowledgeBaseId, {
      name: trimmedName,
      description: editDescription.value.trim() || null,
      routing_description:
        editRoutingDescription.value.trim() || null,
    })
    cancelEditBase()
  })
}

async function toggleBaseActive(
  base: KnowledgeBase,
): Promise<void> {
  closeBaseMenu()
  const nextActive = !base.is_active
  const actionLabel = nextActive ? '启用' : '停用'

  if (
    !window.confirm(
      `确定${actionLabel}“${base.name}”吗？` +
        (nextActive
          ? '\n启用后会重新参与知识检索和自动路由。'
          : '\n停用后不会参与知识检索和自动路由，也不能继续上传文档。'),
    )
  ) {
    return
  }

  await runSafely(async () => {
    await knowledge.setBaseActive(base.id, nextActive)
  })
}

async function removeBase(base: KnowledgeBase): Promise<void> {
  closeBaseMenu()
  if (
    !window.confirm(
      `确定永久删除知识库“${base.name}”吗？\n\n` +
        `将级联清理 ${base.document_count} 个文档、MySQL Chunk、` +
        'Chroma 向量和上传文件。此操作不可恢复。',
    )
  ) {
    return
  }

  await runSafely(async () => {
    await knowledge.deleteBase(base.id)
    if (editingBaseId.value === base.id) {
      cancelEditBase()
    }
  })
}

function onFileChange(event: Event): void {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
}

async function upload(): Promise<void> {
  if (!selectedFile.value) {
    pageError.value = '请选择 .txt / .md / .pdf 文档'
    return
  }

  await runSafely(async () => {
    await knowledge.uploadDocument(
      selectedFile.value as File,
      priority.value,
    )
    selectedFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  })
}

async function removeDocument(
  documentId: number,
  documentName: string,
): Promise<void> {
  if (
    !window.confirm(
      `确定删除“${documentName}”吗？\n\n` +
        '删除会同步清理 MySQL、Chroma 向量和磁盘文件。',
    )
  ) {
    return
  }

  await runSafely(async () => {
    await knowledge.deleteDocument(documentId)
  })
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function statusLabel(status: string): string {
  if (status === 'ready') return '已就绪'
  if (status === 'processing') return '处理中'
  if (status === 'failed') return '失败'
  return status
}

function logout(): void {
  knowledge.reset()
  auth.logout()
  void router.replace('/login')
}
</script>

<template>
  <main class="knowledge-page" @click="closeBaseMenu">
    <header class="page-header">
      <div>
        <p>AI CUSTOMER SERVICE</p>
        <h1>知识库管理</h1>
      </div>

      <div class="header-actions">
        <button
          class="secondary-button"
          type="button"
          @click="router.push('/')"
        >
          返回客服
        </button>

        <div class="user-chip">
          <span>
            {{ accountLabel.slice(0, 1).toUpperCase() }}
          </span>
          <strong>{{ accountLabel }}</strong>
        </div>

        <button
          class="secondary-button"
          type="button"
          @click="logout"
        >
          退出
        </button>
      </div>
    </header>

    <div v-if="pageError" class="page-alert">
      {{ pageError }}
    </div>

    <div class="management-shell">
      <aside class="base-panel">
        <div class="panel-heading">
          <div>
            <p>KNOWLEDGE BASES</p>
            <h2>企业知识库</h2>
          </div>
          <button
            class="small-primary"
            type="button"
            @click="showCreateForm = !showCreateForm"
          >
            + 新建
          </button>
        </div>

        <form
          v-if="showCreateForm"
          class="create-form"
          @submit.prevent="createBase"
        >
          <label>
            名称
            <input
              v-model="name"
              maxlength="128"
              placeholder="例如：退款政策"
            />
          </label>

          <label>
            描述
            <textarea
              v-model="description"
              rows="2"
              maxlength="4000"
              placeholder="这个知识库包含什么内容"
            ></textarea>
          </label>

          <label>
            路由描述
            <textarea
              v-model="routingDescription"
              rows="2"
              maxlength="4000"
              placeholder="例如：退款、到账、售后"
            ></textarea>
          </label>

          <div class="form-actions">
            <button
              type="button"
              class="text-button"
              @click="showCreateForm = false"
            >
              取消
            </button>
            <button
              type="submit"
              class="small-primary"
              :disabled="knowledge.creating"
            >
              {{
                knowledge.creating
                  ? '创建中...'
                  : '创建知识库'
              }}
            </button>
          </div>
        </form>

        <div
          v-if="knowledge.loadingBases"
          class="panel-state"
        >
          正在读取知识库...
        </div>

        <div
          v-else-if="knowledge.bases.length === 0"
          class="panel-state"
        >
          还没有知识库，请先新建。
        </div>

        <div
          v-for="item in knowledge.bases"
          :key="item.id"
          class="base-row"
          :class="{
            active: item.id === knowledge.selectedBaseId,
            inactive: !item.is_active,
          }"
        >
          <button
            class="base-card"
            type="button"
            @click="chooseBase(item.id)"
          >
            <div class="base-card-title">
              <strong>{{ item.name }}</strong>
              <span
                :class="{ enabled: item.is_active }"
              >
                {{ item.is_active ? '启用' : '停用' }}
              </span>
            </div>

            <p>
              {{
                item.description ||
                item.routing_description ||
                '暂无描述'
              }}
            </p>

            <div class="base-meta">
              <span>{{ item.document_count }} 个文档</span>
              <span>{{ relativeApiTime(item.created_at) }}</span>
            </div>
          </button>

          <div class="base-actions" @click.stop>
            <button
              class="base-menu-button"
              type="button"
              :disabled="
                knowledge.updatingBaseId === item.id ||
                knowledge.deletingBaseId === item.id
              "
              :aria-expanded="openMenuBaseId === item.id"
              :aria-label="`管理知识库：${item.name}`"
              title="管理知识库"
              @click="toggleBaseMenu(item.id)"
            >
              ···
            </button>

            <div
              v-if="openMenuBaseId === item.id"
              class="base-menu"
              role="menu"
            >
              <button
                type="button"
                role="menuitem"
                @click="startEditBase(item)"
              >
                编辑
              </button>
              <button
                type="button"
                role="menuitem"
                @click="toggleBaseActive(item)"
              >
                {{ item.is_active ? '停用' : '启用' }}
              </button>
              <button
                class="danger"
                type="button"
                role="menuitem"
                @click="removeBase(item)"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      </aside>

      <section class="document-panel">
        <div v-if="knowledge.selectedBase" class="selected-header">
          <div>
            <p>当前知识库</p>
            <h2>{{ knowledge.selectedBase.name }}</h2>
            <span>
              {{
                knowledge.selectedBase.routing_description ||
                '未配置路由描述'
              }}
            </span>
            <span
              v-if="!knowledge.selectedBase.is_active"
              class="inactive-notice"
            >
              当前知识库已停用，不参与 RAG 检索与自动路由。
            </span>
          </div>

          <div class="pipeline-note">
            文件 → 解析 → Chunk → Embedding → Chroma → MySQL
          </div>
        </div>

        <div
          v-if="knowledge.selectedBase"
          class="upload-card"
          :class="{ disabled: !knowledge.selectedBase.is_active }"
        >
          <div class="upload-copy">
            <strong>上传知识文档</strong>
            <p v-if="knowledge.selectedBase.is_active">
              支持 .txt / .md / .pdf。上传后会自动完成解析、切片、
              qwen3-embedding 向量化并写入 Chroma。
            </p>
            <p v-else class="upload-disabled-copy">
              当前知识库已停用。请先从左侧 ··· 菜单重新启用后再上传。
            </p>
          </div>

          <input
            ref="fileInput"
            type="file"
            accept=".txt,.md,.pdf"
            @change="onFileChange"
          />

          <label class="priority-field">
            优先级
            <input
              v-model.number="priority"
              type="number"
              min="0"
            />
          </label>

          <button
            class="upload-button"
            type="button"
            :disabled="
              !selectedFile ||
              knowledge.uploading ||
              !knowledge.selectedBase.is_active
            "
            @click="upload"
          >
            {{
              knowledge.uploading
                ? '正在解析并向量化...'
                : '上传并入库'
            }}
          </button>
        </div>

        <div
          v-if="!knowledge.selectedBase"
          class="empty-main"
        >
          <div>KB</div>
          <h2>先创建一个知识库</h2>
          <p>
            创建后即可上传文档并自动构建 RAG 检索索引。
          </p>
        </div>

        <div v-else class="document-section">
          <div class="document-heading">
            <div>
              <p>DOCUMENTS</p>
              <h3>文档列表</h3>
            </div>
            <span>
              {{ knowledge.documents.length }} 个文档
            </span>
          </div>

          <div
            v-if="knowledge.loadingDocuments"
            class="panel-state"
          >
            正在读取文档...
          </div>

          <div
            v-else-if="knowledge.documents.length === 0"
            class="document-empty"
          >
            当前知识库还没有文档。
          </div>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>文档</th>
                  <th>状态</th>
                  <th>大小</th>
                  <th>Chunk</th>
                  <th>上传时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="document in knowledge.documents"
                  :key="document.id"
                >
                  <td>
                    <strong>{{ document.original_name }}</strong>
                    <span>{{ document.file_extension }}</span>
                    <small
                      v-if="document.error_message"
                      class="error-copy"
                    >
                      {{ document.error_message }}
                    </small>
                  </td>
                  <td>
                    <span
                      class="status-badge"
                      :class="document.status"
                    >
                      {{ statusLabel(document.status) }}
                    </span>
                  </td>
                  <td>{{ formatBytes(document.file_size_bytes) }}</td>
                  <td>{{ document.chunk_count }}</td>
                  <td>
                    {{ relativeApiTime(document.created_at) }}
                  </td>
                  <td class="actions-cell">
                    <button
                      class="delete-button"
                      type="button"
                      :disabled="
                        knowledge.deletingDocumentId ===
                        document.id
                      "
                      @click="
                        removeDocument(
                          document.id,
                          document.original_name,
                        )
                      "
                    >
                      {{
                        knowledge.deletingDocumentId ===
                        document.id
                          ? '删除中...'
                          : '删除'
                      }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>

    <div
      v-if="editingBaseId !== null"
      class="modal-backdrop"
      @click.stop="cancelEditBase"
    >
      <form
        class="edit-modal"
        @click.stop
        @submit.prevent="saveEditBase"
      >
        <div class="modal-heading">
          <div>
            <p>KNOWLEDGE BASE</p>
            <h3>编辑知识库</h3>
          </div>
          <button
            class="modal-close"
            type="button"
            aria-label="关闭编辑窗口"
            @click="cancelEditBase"
          >
            ×
          </button>
        </div>

        <label>
          名称
          <input
            v-model="editName"
            maxlength="128"
            autofocus
          />
        </label>

        <label>
          描述
          <textarea
            v-model="editDescription"
            rows="3"
            maxlength="4000"
            placeholder="这个知识库包含什么内容"
          ></textarea>
        </label>

        <label>
          路由描述
          <textarea
            v-model="editRoutingDescription"
            rows="3"
            maxlength="4000"
            placeholder="例如：退款、到账、售后"
          ></textarea>
        </label>

        <p class="edit-tip">
          路由描述会影响多知识库自动路由，请使用能明确区分业务域的关键词。
        </p>

        <div class="modal-actions">
          <button
            class="secondary-button"
            type="button"
            @click="cancelEditBase"
          >
            取消
          </button>
          <button
            class="small-primary"
            type="submit"
            :disabled="knowledge.updatingBaseId !== null"
          >
            {{
              knowledge.updatingBaseId !== null
                ? '保存中...'
                : '保存修改'
            }}
          </button>
        </div>
      </form>
    </div>
  </main>
</template>

<style scoped>
.knowledge-page {
  min-height: 100vh;
  background: #f5f7fb;
  color: #172033;
}

.page-header {
  display: flex;
  min-height: 76px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 28px;
  border-bottom: 1px solid #e4e9f1;
  background: rgb(255 255 255 / 90%);
}

.page-header p,
.panel-heading p,
.document-heading p,
.selected-header p {
  margin: 0 0 4px;
  color: #8a93a6;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .13em;
}

.page-header h1,
.panel-heading h2,
.selected-header h2,
.document-heading h3 {
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.secondary-button,
.small-primary,
.upload-button,
.text-button,
.delete-button {
  border-radius: 9px;
  font-weight: 800;
  cursor: pointer;
}

.secondary-button {
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid #dfe4ec;
  background: #fff;
  color: #59647a;
}

.small-primary,
.upload-button {
  border: 0;
  background: #3159d8;
  color: #fff;
}

.small-primary {
  min-height: 34px;
  padding: 0 12px;
}

.user-chip {
  display: flex;
  min-height: 36px;
  align-items: center;
  gap: 7px;
  padding: 0 9px 0 6px;
  border: 1px solid #e0e5ed;
  border-radius: 11px;
  background: #fff;
}

.user-chip span {
  display: grid;
  width: 25px;
  height: 25px;
  place-items: center;
  border-radius: 8px;
  background: #172033;
  color: #fff;
  font-size: 10px;
  font-weight: 900;
}

.user-chip strong {
  max-width: 150px;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.management-shell {
  display: grid;
  min-height: calc(100vh - 77px);
  grid-template-columns: 310px minmax(0, 1fr);
}

.base-panel {
  padding: 22px 16px;
  border-right: 1px solid #e4e9f1;
  background: #fbfcfe;
}

.panel-heading,
.document-heading,
.selected-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.create-form {
  display: grid;
  gap: 11px;
  margin: 17px 0;
  padding: 14px;
  border: 1px solid #dfe5ee;
  border-radius: 13px;
  background: #fff;
}

.create-form label {
  display: grid;
  gap: 5px;
  color: #566177;
  font-size: 11px;
  font-weight: 750;
}

.create-form input,
.create-form textarea,
.priority-field input {
  border: 1px solid #dce2eb;
  border-radius: 9px;
  outline: none;
  padding: 9px 10px;
  color: #243049;
  font: inherit;
}

.create-form input:focus,
.create-form textarea:focus,
.priority-field input:focus {
  border-color: #8da5f1;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.text-button {
  border: 0;
  background: transparent;
  color: #778197;
}

.base-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
  margin-top: 9px;
  border: 1px solid transparent;
  border-radius: 12px;
  transition: background .14s ease, border-color .14s ease;
}

.base-row:hover {
  background: #f1f4f9;
}

.base-row.active {
  border-color: #cdd8f7;
  background: #edf2ff;
}

.base-row.inactive {
  opacity: .78;
}

.base-card {
  display: grid;
  min-width: 0;
  width: 100%;
  gap: 7px;
  padding: 13px 4px 13px 13px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.base-actions {
  position: relative;
  display: grid;
  align-self: stretch;
  place-items: start center;
  padding: 8px 5px 0 0;
}

.base-menu-button {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #7d879b;
  font-size: 16px;
  font-weight: 900;
  line-height: 1;
  opacity: 0;
  cursor: pointer;
}

.base-row:hover .base-menu-button,
.base-row.active .base-menu-button,
.base-menu-button[aria-expanded='true'] {
  opacity: 1;
}

.base-menu-button:hover:not(:disabled) {
  background: #fff;
  color: #26324a;
  box-shadow: 0 4px 12px rgb(31 45 72 / 10%);
}

.base-menu-button:disabled {
  cursor: not-allowed;
  opacity: .35;
}

.base-menu {
  position: absolute;
  z-index: 30;
  top: 38px;
  right: 5px;
  display: grid;
  min-width: 112px;
  padding: 5px;
  border: 1px solid #dde3ee;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 14px 32px rgb(29 43 70 / 16%);
}

.base-menu button {
  padding: 8px 10px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #303a50;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.base-menu button:hover {
  background: #f4f6fa;
}

.base-menu button.danger {
  color: #c54848;
}

.base-menu button.danger:hover {
  background: #fff1f1;
}

.base-card-title,
.base-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.base-card-title strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.base-card-title span {
  color: #a06623;
  font-size: 9px;
}

.base-card-title span.enabled {
  color: #17925f;
}

.base-card p {
  margin: 0;
  color: #7c8599;
  font-size: 10px;
  line-height: 1.6;
}

.base-meta {
  color: #9aa2b1;
  font-size: 9px;
}

.document-panel {
  padding: 28px clamp(20px, 4vw, 54px);
}

.selected-header span {
  display: block;
  margin-top: 6px;
  color: #7c8599;
  font-size: 11px;
}

.pipeline-note {
  padding: 9px 12px;
  border-radius: 9px;
  background: #eef2ff;
  color: #5067bd;
  font-size: 10px;
  font-weight: 750;
}

.upload-card {
  display: grid;
  grid-template-columns: minmax(230px, 1fr) minmax(210px, .8fr) 100px 160px;
  gap: 14px;
  margin-top: 22px;
  padding: 18px;
  align-items: center;
  border: 1px solid #dfe5ee;
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 10px 30px rgb(33 46 75 / 5%);
}

.upload-copy strong {
  font-size: 13px;
}

.upload-copy p {
  margin: 5px 0 0;
  color: #788297;
  font-size: 10px;
  line-height: 1.6;
}

.priority-field {
  display: grid;
  gap: 4px;
  color: #778197;
  font-size: 9px;
}

.priority-field input {
  width: 100%;
  box-sizing: border-box;
}

.upload-button {
  min-height: 40px;
  padding: 0 12px;
}

.upload-button:disabled,
.small-primary:disabled,
.delete-button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.inactive-notice {
  width: fit-content;
  padding: 5px 8px;
  border-radius: 7px;
  background: #fff2e3;
  color: #a5641d !important;
  font-weight: 750;
}

.upload-card.disabled {
  background: #fafbfd;
}

.upload-disabled-copy {
  color: #a5641d !important;
  font-weight: 700;
}

.modal-backdrop {
  position: fixed;
  z-index: 100;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(17 28 49 / 34%);
  backdrop-filter: blur(2px);
}

.edit-modal {
  display: grid;
  width: min(520px, 100%);
  gap: 14px;
  padding: 20px;
  border: 1px solid #dfe5ee;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 24px 70px rgb(18 31 55 / 22%);
}

.modal-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.modal-heading p {
  margin: 0 0 4px;
  color: #8a93a6;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .13em;
}

.modal-heading h3 {
  margin: 0;
  color: #172033;
  font-size: 18px;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 9px;
  background: #f3f5f8;
  color: #657086;
  font-size: 20px;
  cursor: pointer;
}

.edit-modal label {
  display: grid;
  gap: 6px;
  color: #566177;
  font-size: 11px;
  font-weight: 750;
}

.edit-modal input,
.edit-modal textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 11px;
  border: 1px solid #dce2eb;
  border-radius: 9px;
  outline: none;
  color: #243049;
  font: inherit;
}

.edit-modal input:focus,
.edit-modal textarea:focus {
  border-color: #8da5f1;
}

.edit-tip {
  margin: -2px 0 0;
  color: #8a93a6;
  font-size: 10px;
  line-height: 1.6;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.document-section {
  margin-top: 28px;
}

.document-heading {
  align-items: end;
}

.document-heading span {
  color: #8f98aa;
  font-size: 10px;
}

.table-wrap {
  margin-top: 12px;
  overflow-x: auto;
  border: 1px solid #e0e5ed;
  border-radius: 14px;
  background: #fff;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 13px 14px;
  border-bottom: 1px solid #edf0f4;
  color: #566177;
  font-size: 11px;
  text-align: left;
  vertical-align: top;
}

th {
  background: #fafbfd;
  color: #8a93a6;
  font-size: 9px;
  letter-spacing: .06em;
}

td strong {
  display: block;
  color: #273149;
}

td > span:not(.status-badge) {
  display: inline-block;
  margin-top: 4px;
  color: #969fb0;
  font-size: 9px;
}

.error-copy {
  display: block;
  max-width: 420px;
  margin-top: 5px;
  color: #b34848;
  line-height: 1.5;
}

.status-badge {
  display: inline-block;
  padding: 4px 7px;
  border-radius: 7px;
  background: #eef1f5;
  font-size: 9px;
  font-weight: 850;
}

.status-badge.ready {
  background: #e8f7ef;
  color: #138154;
}

.status-badge.processing {
  background: #eef2ff;
  color: #4e65c2;
}

.status-badge.failed {
  background: #fff0f0;
  color: #b54141;
}

.actions-cell {
  text-align: right;
}

.delete-button {
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid #f0cccc;
  background: #fff;
  color: #b34747;
}

.panel-state,
.document-empty,
.empty-main {
  color: #8c95a7;
  text-align: center;
}

.panel-state {
  padding: 24px 10px;
  font-size: 11px;
}

.document-empty {
  margin-top: 12px;
  padding: 42px 15px;
  border: 1px dashed #d8dee8;
  border-radius: 13px;
  font-size: 11px;
}

.empty-main {
  display: grid;
  min-height: 60vh;
  place-content: center;
}

.empty-main div {
  display: grid;
  width: 54px;
  height: 54px;
  margin: 0 auto 14px;
  place-items: center;
  border-radius: 17px;
  background: #172033;
  color: #fff;
  font-weight: 900;
}

.empty-main h2 {
  margin: 0;
  color: #273149;
}

.empty-main p {
  margin: 8px 0 0;
  font-size: 11px;
}

.page-alert {
  position: fixed;
  z-index: 20;
  top: 88px;
  right: 22px;
  max-width: 410px;
  padding: 11px 14px;
  border: 1px solid #f0c6c6;
  border-radius: 10px;
  background: #fff2f2;
  color: #a33b3b;
  font-size: 11px;
  box-shadow: 0 10px 25px rgb(80 30 30 / 8%);
}

@media (max-width: 1050px) {
  .management-shell {
    grid-template-columns: 250px minmax(0, 1fr);
  }

  .upload-card {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 760px) {
  .management-shell {
    display: block;
  }

  .base-panel {
    border-right: 0;
    border-bottom: 1px solid #e4e9f1;
  }

  .upload-card {
    grid-template-columns: 1fr;
  }

  .user-chip strong {
    display: none;
  }
}
</style>
