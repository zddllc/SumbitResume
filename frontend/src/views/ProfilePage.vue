<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import ResumeEditor from '../components/ResumeEditor.vue'
import NoticeBanner from '../components/NoticeBanner.vue'
import TaskList from '../components/TaskList.vue'
import { api } from '../lib/api'
import { auth } from '../lib/auth'
import { activeTask, dateText, emptyResume, errorText, useAction, usePolling } from '../lib/forms'
import type { AppState, ResumeRecord, Task } from '../types'

const record = ref<ResumeRecord | null>(null)
const draft = ref(emptyResume())
const token = ref(''), dirty = ref(false), facts = ref(false), updated = ref(false)
const file = ref<File | null>(null), consent = ref(false), tasks = ref<Task[]>([])
const { busy, message, run } = useAction()
let loaded = false
const status = computed(() => dirty.value ? '底板有未保存修改，请核对后确认保存。'
  : record.value?.draft ? `新解析结果待确认：${record.value.draft_filename || '上传简历'}。确认前仍使用上一份已确认底板。`
    : record.value?.confirmed ? `已加载保存的底板 · ${dateText(record.value.confirmed_at)}。可直接修改，无需调用模型。`
      : '尚无底板。请先配置模型，再上传已有简历。')
function changed() { dirty.value = true; facts.value = false }
async function load(force = false) {
  const data = await api<AppState>('state')
  tasks.value = data.tasks
  const incoming = data.resume?.edit_token || ''
  if (!force && dirty.value) { updated.value = incoming !== token.value; return }
  if (!force && loaded && incoming === token.value) return
  record.value = data.resume
  draft.value = structuredClone(data.resume?.draft || data.resume?.confirmed || emptyResume())
  token.value = incoming
  dirty.value = false; facts.value = false; updated.value = false; loaded = true
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
async function reload() {
  if (dirty.value && !window.confirm('重新加载会丢弃尚未保存的修改，是否继续？')) return
  await run(() => load(true))
}
async function cancel(id: string) { await run(async () => { await api(`tasks/${id}/cancel`, 'POST'); await load() }) }
onBeforeRouteLeave(() => !auth.user || !dirty.value || window.confirm('底板修改尚未保存，是否离开？'))
</script>
<template>
  <header class="page-heading"><div><span class="eyebrow">SOURCE OF TRUTH</span><h1>简历底板</h1><p class="muted">已有底板自动加载，可直接编辑。只有已确认的事实用于后续定制。</p></div></header>
  <NoticeBanner :message="message" />
  <details class="card" :open="!record?.confirmed">
    <summary>{{ record?.confirmed ? '重新上传或替换文件（可选）' : '上传简历文件' }}</summary>
    <form class="stack" @submit.prevent="upload"><fieldset :disabled="busy" class="stack">
      <label>Word / PDF（最多 10 MB）<input type="file" accept=".docx,.pdf" required @change="choose"></label>
      <label class="check"><input v-model="consent" type="checkbox" required>同意将简历文字发送给已配置的模型服务解析。</label>
      <p class="hint">支持 DOCX 和有文字层的 PDF；不支持旧版 DOC、加密 PDF 和扫描件 OCR。原文件不持久保存。</p>
      <button type="submit">上传并解析为结构化底板</button>
    </fieldset></form>
  </details>
  <section v-if="tasks.some(activeTask)" class="card"><h2>后台任务</h2><TaskList :tasks="tasks" :disabled="busy" @cancel="cancel" /></section>
  <section class="card">
    <div class="section-heading"><h2>编辑简历底板</h2><button type="button" class="secondary small" :disabled="busy" @click="reload">重新加载底板</button></div>
    <p class="notice" :class="{ warning: dirty }">{{ status }}</p>
    <p v-if="updated" class="notice warning">后台已有新版本，当前未保存修改已保留。点击重新加载可切换。</p>
    <form @submit.prevent="save"><fieldset :disabled="busy" class="stack">
      <ResumeEditor v-model="draft" @change="changed" />
      <label class="check"><input v-model="facts" type="checkbox" required>我已核对并确认底板真实、准确，可用于后续职位定制。</label>
      <button type="submit" :disabled="!token || !facts">{{ record?.confirmed && !record?.draft ? '确认并保存修改' : '确认并保存底板' }}</button>
    </fieldset></form>
  </section>
</template>
