<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import ResumeEditor from '../components/ResumeEditor.vue'
import ResumeImportReview from '../components/ResumeImportReview.vue'
import NoticeBanner from '../components/NoticeBanner.vue'
import TaskList from '../components/TaskList.vue'
import { api } from '../lib/api'
import { auth } from '../lib/auth'
import { activeTask, dateText, emptyResume, errorText, useAction, usePolling } from '../lib/forms'
import type { AppState, ResumeProfile, ResumeRecord, Task } from '../types'

const record = ref<ResumeRecord | null>(null)
const draft = ref(emptyResume())
const token = ref(''), dirty = ref(false), facts = ref(false), updated = ref(false)
const comparisonDirty = ref(false)
const file = ref<File | null>(null), consent = ref(false), tasks = ref<Task[]>([])
const { busy, message, run } = useAction()
let loaded = false
const status = computed(() => dirty.value ? '底板有未保存修改，请核对后确认保存。'
  : record.value?.pending_import ? '新上传内容等待对比，当前草稿和已确认底板均保持不变。'
    : record.value?.draft ? '已加载保存的草稿，可逐条修改或删除。确认前仍使用上一份已确认底板。'
    : record.value?.confirmed ? `已加载保存的底板 · ${dateText(record.value.confirmed_at)}。可直接修改，无需调用模型。`
      : '尚无底板。请先配置模型，再上传已有简历。')
function changed() { dirty.value = true; facts.value = false }
async function load(force = false) {
  const data = await api<AppState>('state')
  tasks.value = data.tasks
  const incoming = data.resume?.edit_token || ''
  const sameImport = data.resume?.pending_import?.id === record.value?.pending_import?.id
  if (!force && (dirty.value || comparisonDirty.value)) {
    updated.value = incoming !== token.value || (comparisonDirty.value && !sameImport)
    if (!comparisonDirty.value || sameImport) record.value = data.resume
    return
  }
  if (!force && loaded && incoming === token.value && sameImport) return
  const profile = structuredClone(data.resume?.draft || data.resume?.confirmed || emptyResume())
  record.value = data.resume
  draft.value = profile
  token.value = incoming
  dirty.value = false; comparisonDirty.value = false; facts.value = false; updated.value = false; loaded = true
}
onMounted(() => run(() => load(true)))
usePolling(() => load(), () => !busy.value && tasks.value.some(activeTask), error => { message.value = { text: errorText(error), kind: 'error' } })
function choose(event: Event) {
  if (!(event.target instanceof HTMLInputElement)) throw new Error('文件控件异常')
  file.value = event.target.files?.item(0) || null
}
async function upload() {
  await run(async () => {
    if (!file.value || !consent.value) throw new Error('请选择文件并确认模型调用授权')
    if (file.value.size > 10 * 1024 * 1024) throw new Error('简历文件不能超过 10 MB')
    const data = new FormData()
    data.set('file', file.value); data.set('consent', 'yes')
    await api<{ task_id: string }>('resume/upload', 'POST', data)
    await load()
  }, '解析任务已开始，完成后请核对结构化内容并确认。')
}
async function save() {
  await run(async () => {
    await api('resume/confirm', 'POST', { edit_token: token.value, profile: draft.value })
    dirty.value = false
    try { await load(true) } catch { throw new Error('底板已保存，但界面刷新失败，请重新加载。') }
  }, '底板已确认保存，之后的定制使用这份内容。')
}
async function applyImport(profile: ResumeProfile) {
  await run(async () => {
    if (!record.value?.pending_import) throw new Error('上传结果不存在，请重新加载')
    await api('resume/import/apply', 'POST', {
      edit_token: token.value, import_id: record.value.pending_import.id, profile,
    })
    dirty.value = false; comparisonDirty.value = false
    try { await load(true) } catch { throw new Error('所选内容已保存为草稿，但刷新失败，请重新加载。') }
  }, '所选内容已保存为草稿，可继续单条修改或删除；已确认底板尚未改变。')
}
async function discardImport() {
  await run(async () => {
    if (!record.value?.pending_import) throw new Error('上传结果不存在，请重新加载')
    await api('resume/import/discard', 'POST', {
      edit_token: token.value, import_id: record.value.pending_import.id,
    })
    comparisonDirty.value = false
    await load()
  }, '已放弃本次上传，原有内容保持不变。')
}
async function reload() {
  if ((dirty.value || comparisonDirty.value) && !window.confirm('重新加载会丢弃尚未保存的修改和对比选择，是否继续？')) return
  await run(() => load(true))
}
async function cancel(id: string) { await run(async () => { await api(`tasks/${id}/cancel`, 'POST'); await load() }) }
onBeforeRouteLeave(() => !auth.user || (!dirty.value && !comparisonDirty.value) || window.confirm('底板修改或对比选择尚未保存，是否离开？'))
</script>
<template>
  <header class="page-heading"><div><span class="eyebrow">SOURCE OF TRUTH</span><h1>简历底板</h1><p class="muted">已有底板自动加载，可直接编辑。只有已确认的事实用于后续定制。</p></div></header>
  <NoticeBanner :message="message" />
  <details class="card" :open="!record?.confirmed">
    <summary>{{ record?.confirmed || record?.draft ? '上传文件并对比补充（可选）' : '上传简历文件' }}</summary>
    <form class="stack" @submit.prevent="upload"><fieldset :disabled="busy || !!record?.pending_import || tasks.some(activeTask)" class="stack">
      <label>Word / PDF（最多 10 MB）<input type="file" accept=".docx,.pdf" required @change="choose"></label>
      <label class="check"><input v-model="consent" type="checkbox" required>同意将简历文字发送给已配置的模型服务解析，并保存请求和响应用于审核。</label>
      <p class="hint">支持 DOCX 和有文字层的 PDF；不支持旧版 DOC、加密 PDF 和扫描件 OCR。原文件不持久保存；模型请求中的文字和原始响应会留存在数据库，不记录认证头和 API key。</p>
      <p class="hint">新解析内容先单独保存，完成新旧对比后才按你的选择更新草稿，不会自动覆盖现有内容。</p>
      <button type="submit">上传并解析为结构化底板</button>
    </fieldset></form>
  </details>
  <section v-if="tasks.some(activeTask)" class="card"><h2>后台任务</h2><TaskList :tasks="tasks" :disabled="busy" @cancel="cancel" /></section>
  <ResumeImportReview v-if="record?.pending_import" :key="`${record.pending_import.id}:${token}`" :current="draft" :incoming="record.pending_import.profile" :filename="record.pending_import.filename" :disabled="busy || updated" @change="comparisonDirty = true" @apply="applyImport" @discard="discardImport" />
  <p v-if="updated" class="notice warning">后台底板已有新版本，当前未保存内容已保留。请点击“重新加载底板”后再操作，避免覆盖。</p>
  <section class="card">
    <div class="section-heading"><h2>编辑简历底板</h2><button type="button" class="secondary small" :disabled="busy" @click="reload">重新加载底板</button></div>
    <p class="notice" :class="{ warning: dirty }">{{ status }}</p>
    <p v-if="record?.pending_import" class="hint">请先在上方应用选择或放弃上传，再逐条编辑、删除并确认底板。</p>
    <form @submit.prevent="save"><fieldset :disabled="busy || !!record?.pending_import || updated" class="stack">
      <ResumeEditor v-model="draft" @change="changed" />
      <label class="check"><input v-model="facts" type="checkbox" required>我已核对并确认底板真实、准确，可用于后续职位定制。</label>
      <button type="submit" :disabled="!token || !facts">{{ record?.confirmed && !record?.draft ? '确认并保存修改' : '确认并保存底板' }}</button>
    </fieldset></form>
  </section>
</template>
