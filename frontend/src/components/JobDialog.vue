<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api, apiUrl } from '../lib/api'
import { auth } from '../lib/auth'
import { activeTask, dateText, emptyResume, errorText, useAction, usePolling } from '../lib/forms'
import { fillResumeGaps } from '../lib/resumeImport'
import type { ApplicationInfo, JobDetail, LatestSource, PdfArtifact, ResumeProfile, TailoredResume, Task, TemplateCatalog } from '../types'
import ResumeEditor from './ResumeEditor.vue'
import ResumePreview from './ResumePreview.vue'
import NoticeBanner from './NoticeBanner.vue'

const props = defineProps<{ jobId: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const info = ref<JobDetail | null>(null), current = ref<TailoredResume | null>(null)
const draft = ref<ResumeProfile>(emptyResume()), versionId = ref(''), dirty = ref(false), facts = ref(false)
const consent = ref(false), generationId = ref(''), generation = ref<Task | null>(null)
const templates = ref<TemplateCatalog | null>(null), templateId = ref('')
const initialTemplateId = ref('')
const latestSource = ref<LatestSource | null>(null), sourceError = ref('')
const pdfPhase = ref<'idle' | 'generating' | 'completed' | 'failed' | 'unverified'>('idle')
const pdfError = ref('')
const resultLoading = ref(false)
let sourceRequest = 0
let generationChecking = false
const { busy, message, run } = useAction()
const modelRunning = computed(() => resultLoading.value || Boolean(generationId.value && (!generation.value || activeTask(generation.value))))
const templateChanged = computed(() => Boolean(current.value && templateId.value !== initialTemplateId.value))
const unsaved = computed(() => dirty.value || templateChanged.value)
const ready = computed(() => Boolean(current.value?.pdf_ready && !unsaved.value && !modelRunning.value && !['generating', 'failed', 'unverified'].includes(pdfPhase.value)))
const pdfStatus = computed(() => {
  if (pdfPhase.value === 'generating') return '正在制作 PDF：排版、校验并保存文件，请稍候。完成后会显示下载按钮。'
  if (modelRunning.value) return '正在生成新的职位简历内容，完成并核对后再制作 PDF；原来保存的文件尚未改变。'
  if (pdfPhase.value === 'unverified') return 'PDF 已提交保存，但未能核验最新文件状态；请点击“加载最新结果”，核验后再下载。'
  if (pdfPhase.value === 'failed') return `PDF 生成失败：${pdfError.value}。当前编辑已保留，可直接重试；旧文件状态可通过“加载最新结果”重新核验。`
  if (unsaved.value) return `${templateChanged.value ? '模板已更换；' : ''}当前内容或模板尚未生成对应 PDF，请核对后生成。`
  if (ready.value) return `PDF 已完成，可以下载 · ${dateText(current.value?.pdf?.created_at || current.value?.reviewed_at)}`
  return current.value ? '尚无可下载的 PDF，请核对内容并确认生成。' : '尚无职位简历，请先使用底板生成内容。'
})
const pdfUrl = computed(() => current.value
  ? apiUrl(`tailored/${current.value.id}/pdf?v=${encodeURIComponent(current.value.pdf?.file_id || current.value.edit_token)}`) : '')
const application = computed<ApplicationInfo>(() => current.value?.application || {
  kind: info.value?.job.application_kind || 'unavailable', url: info.value?.job.application_url, error: info.value?.job.application_error,
})
const applicationLink = computed(() => {
  if (application.value.kind !== 'external' || !application.value.url) return null
  try {
    const url = new URL(application.value.url)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null
  } catch { return null }
})
const applicationNote = computed(() => application.value.kind === 'easy_apply'
  ? 'LinkedIn 站内易申请，没有独立外站链接。'
  : applicationLink.value ? '申请入口已保存，无需回到 LinkedIn 寻找。先确认 PDF，再进入申请网站。'
    : application.value.error || '尚无可用申请入口，重新采集可更新。')
const job = computed(() => current.value?.job || info.value?.job)
function changed() { dirty.value = true; facts.value = false; pdfPhase.value = 'idle'; pdfError.value = '' }
function canDiscard() { return !unsaved.value || window.confirm('这份职位简历或模板的修改尚未保存，是否丢弃？') }
function selectTemplate() { facts.value = false; pdfPhase.value = 'idle'; pdfError.value = '' }
function close() { if (!busy.value && !modelRunning.value && canDiscard()) emit('close') }
function cancel(event: Event) { event.preventDefault(); close() }
onBeforeRouteLeave(() => {
  if (!auth.user) return true
  if (busy.value || modelRunning.value) {
    message.value = { text: '请求仍在进行，请稍候再离开。', kind: 'info' }
    return false
  }
  return canDiscard()
})
async function version(id: string) {
  sourceRequest++
  const loaded = await api<TailoredResume>(`tailored/${encodeURIComponent(id)}`)
  const editable = structuredClone(loaded.resume)
  current.value = loaded
  latestSource.value = loaded.latest_source || null
  sourceError.value = ''
  versionId.value = id
  draft.value = editable
  templateId.value = loaded.template_id || (loaded.pdf_ready ? 'simple' : templates.value?.default_template_id || '')
  initialTemplateId.value = templateId.value
  dirty.value = false; facts.value = false; pdfPhase.value = 'idle'; pdfError.value = ''
}
async function load() {
  const [catalog, details] = await Promise.all([
    api<TemplateCatalog>('resume-templates'), api<JobDetail>(`jobs/${encodeURIComponent(props.jobId)}`),
  ])
  templates.value = catalog
  info.value = details
  const latest = info.value.versions[0]
  if (latest) await version(latest.id)
  else { current.value = null; versionId.value = ''; dirty.value = false; latestSource.value = null }
}
async function refreshSource() {
  const id = current.value?.id
  if (!id) return
  const request = ++sourceRequest
  const source = await api<LatestSource>(`tailored/${encodeURIComponent(id)}/source`)
  if (current.value?.id === id && request === sourceRequest) { latestSource.value = source; sourceError.value = '' }
}
function sourceFailed(error: unknown) { sourceError.value = `无法检查最新底板：${errorText(error)}` }
function focusSource() {
  if (busy.value) return
  if (modelRunning.value) {
    void checkGeneration().catch(error => { message.value = { text: errorText(error), kind: 'error' } })
  } else void refreshSource().catch(sourceFailed)
}
function visible() { if (document.visibilityState === 'visible') focusSource() }
onMounted(async () => {
  dialog.value?.showModal()
  window.addEventListener('focus', focusSource); document.addEventListener('visibilitychange', visible)
  await run(load)
})
onBeforeUnmount(() => {
  dialog.value?.close()
  window.removeEventListener('focus', focusSource); document.removeEventListener('visibilitychange', visible)
})
usePolling(refreshSource, () => Boolean(current.value && !busy.value && !modelRunning.value && document.visibilityState !== 'hidden'), sourceFailed, 10000)
async function selectVersion(event: Event) {
  if (!(event.target instanceof HTMLSelectElement)) throw new Error('版本控件异常')
  const id = event.target.value
  if (!canDiscard()) { event.target.value = versionId.value; return }
  await run(() => version(id))
}
async function reload() {
  if (!canDiscard()) return
  await run(async () => {
    if (generation.value?.status === 'succeeded' && generation.value.result_resume_id) await loadGenerated(generation.value)
    else await load()
  })
}
async function fillBlanks() {
  await run(async () => {
    await refreshSource()
    if (!latestSource.value?.confirmed) throw new Error('还没有已确认底板，请先在 Profile 确认保存')
    const filled = fillResumeGaps(draft.value, latestSource.value.confirmed)
    if (JSON.stringify(filled) === JSON.stringify(draft.value)) {
      message.value = { text: '没有可安全补齐的空白；已有内容与不明确的条目均保持不变。', kind: 'info' }
      return
    }
    draft.value = filled
    changed()
    message.value = { text: '已从最新已确认底板补齐空白，未覆盖已有内容。请核对后生成 PDF；未调用模型。', kind: 'success' }
  })
}
async function confirm() {
  await run(async () => {
    if (!current.value || !facts.value || !templateId.value) throw new Error('请选择模板并核对后确认')
    const id = current.value.id
    pdfPhase.value = 'generating'; pdfError.value = ''
    let saved = false
    try {
      const result = await api<{ pdf?: PdfArtifact }>(`tailored/${id}/review`, 'POST', {
        confirmed: true, edit_token: current.value.edit_token, profile: draft.value, template_id: templateId.value,
      })
      saved = true
      const loaded = await api<TailoredResume>(`tailored/${encodeURIComponent(id)}`)
      if (!loaded.pdf_ready || (result.pdf && loaded.pdf?.file_id !== result.pdf.file_id)) {
        throw new Error('最新 PDF 尚未通过就绪核验，请加载最新结果')
      }
      const editable = structuredClone(loaded.resume)
      sourceRequest++
      current.value = loaded; draft.value = editable
      latestSource.value = loaded.latest_source || latestSource.value
      sourceError.value = ''
      initialTemplateId.value = templateId.value
      dirty.value = false
      pdfPhase.value = 'completed'
      emit('changed')
    } catch (error) {
      pdfError.value = errorText(error)
      pdfPhase.value = saved ? 'unverified' : 'failed'
      if (saved) emit('changed')
      throw error
    }
  }, '职位简历已确认，投递 PDF 已生成并保存。')
}
async function loadGenerated(task: Task) {
  if (!task.result_resume_id) throw new Error('生成任务缺少结果版本 ID，请加载最新结果或升级后端')
  const details = await api<JobDetail>(`jobs/${encodeURIComponent(props.jobId)}`)
  await version(task.result_resume_id)
  if (current.value && !details.versions.some(item => item.id === task.result_resume_id)) {
    details.versions.unshift(current.value)
  }
  info.value = details
}
async function checkGeneration() {
  if (generationChecking) return
  generationChecking = true
  try {
    const task = await api<Task>(`tasks/${generationId.value}`)
    generation.value = task
    if (!activeTask(task)) {
      emit('changed')
      if (task.status === 'succeeded') {
        resultLoading.value = true
        try {
          await loadGenerated(task)
          message.value = { text: `职位简历内容已${task.cached ? '复用并' : '生成并'}自动加载，请核对后制作 PDF。`, kind: 'success' }
        } finally { resultLoading.value = false }
      } else {
        message.value = { text: task.error || '内容生成任务未完成，当前简历已保留，可重试。', kind: 'error' }
      }
    }
  } finally { generationChecking = false }
}
async function generate() {
  await run(async () => {
    if (!consent.value) throw new Error('请先确认模型调用授权')
    if (!canDiscard()) return
    const result = await api<{ task_id: string }>(`jobs/${encodeURIComponent(props.jobId)}/generate`, 'POST', { consent: true })
    generationId.value = result.task_id
    generation.value = null
    await checkGeneration()
    emit('changed')
  })
}
usePolling(checkGeneration, () => !busy.value && modelRunning.value, error => { message.value = { text: errorText(error), kind: 'error' } })
</script>
<template>
  <dialog ref="dialog" @cancel="cancel">
    <div class="section-heading"><h2>{{ job?.title || '职位详情' }}</h2><button type="button" class="secondary small" :disabled="busy || modelRunning" @click="close">关闭</button></div>
    <p class="muted">{{ [job?.company, job?.location].filter(Boolean).join(' · ') }}</p>
    <div class="button-row">
      <a :href="`https://www.linkedin.com/jobs/view/${encodeURIComponent(jobId)}/`" target="_blank" rel="noopener noreferrer">在 LinkedIn 查看</a>
      <a v-if="applicationLink" :href="applicationLink" target="_blank" rel="noopener noreferrer">打开已保存的申请入口</a>
    </div>
    <p class="hint">{{ applicationNote }}</p>
    <NoticeBanner :message="message" />
    <div v-if="info" class="detail-grid">
      <section><h3>职位描述</h3><pre class="prose">{{ job?.description }}</pre></section>
      <section>
        <h3>定制简历</h3>
        <div class="card stack">
          <p class="hint">内容生成与 PDF 排版是两步。模型使用最新已确认底板和已保存的职位描述；相同输入直接复用，完成后自动加载。</p>
          <p v-if="latestSource" class="notice" :class="{ warning: latestSource.status !== 'current' }" data-source-status>
            {{ latestSource.status === 'changed' ? '底板已变化：当前职位简历仍基于旧底板，可重新使用模型生成内容。' : latestSource.status === 'unknown' ? '当前版本缺少底板来源信息，可按最新已确认底板重新生成。' : latestSource.status === 'unavailable' ? '尚无已确认底板，请先到 Profile 核对并确认保存。' : '当前职位简历基于最新已确认底板。' }}
            <span v-if="latestSource.confirmed_at">最近确认：{{ dateText(latestSource.confirmed_at) }}。</span>
            <span v-if="latestSource.has_pending_changes">Profile 还有未确认草稿或上传结果，这些内容尚不用于生成。</span>
          </p>
          <p v-if="sourceError" class="notice error" role="alert">{{ sourceError }}</p>
          <label class="check"><input v-model="consent" type="checkbox" :disabled="busy">同意把已保存的描述和已确认底板发给配置的模型服务，保存请求和响应用于审核，可能产生费用。</label>
          <div class="button-row">
            <button type="button" class="secondary" :disabled="busy || modelRunning" @click="generate">{{ modelRunning ? '正在生成职位内容…' : latestSource?.status === 'changed' ? '用最新底板重新生成内容（模型）' : '按最新已确认底板生成内容（模型）' }}</button>
            <button v-if="current" type="button" class="secondary" :disabled="busy || modelRunning" @click="fillBlanks">仅补齐空白（不调用模型）</button>
            <button type="button" class="secondary" :disabled="busy || modelRunning" @click="reload">加载最新结果</button>
          </div>
          <p class="hint">仅补齐空白会读取最新底板，不覆盖已有内容；匹配明确的经历补缺失字段，空章节整体补入，不向非空章节擅自追加未知条目。补齐后仍需核对确认。</p>
          <p v-if="generation" class="hint" role="status">{{ generation.status === 'succeeded' ? `内容生成已完成（新生成 ${generation.generated}，复用 ${generation.cached}）。` : generation.error || (modelRunning ? '模型正在生成职位简历内容，请稍候；这还不是 PDF 文件。' : `生成任务：${generation.status}`) }}</p>
        </div>
        <label>历史版本<select :value="versionId" :disabled="busy || modelRunning" @change="selectVersion"><option v-for="item in info.versions" :key="item.id" :value="item.id">{{ dateText(item.created_at) }} · {{ item.llm.model }}</option></select></label>
        <p class="notice" :class="{ warning: !ready, error: pdfPhase === 'failed' || pdfPhase === 'unverified' }" role="status" aria-live="polite" data-pdf-status>{{ pdfStatus }}</p>
        <progress v-if="pdfPhase === 'generating'" aria-label="PDF 正在排版、校验和保存" />
        <div v-if="ready && current" class="button-row">
          <a class="button secondary" :href="pdfUrl" target="_blank" rel="noopener noreferrer">查看已确认 PDF</a>
          <a class="button" :href="`${pdfUrl}&download=1`" download>下载投递 PDF</a>
        </div>
        <form v-if="current" @submit.prevent="confirm"><fieldset :disabled="busy || modelRunning" class="stack">
          <div class="pdf-toolbar">
            <label class="check"><input v-model="facts" type="checkbox" required>我已核对这份职位简历真实、准确，同意生成用于后续投递的 PDF。</label>
            <button type="submit" :disabled="!facts || pdfPhase === 'unverified'">{{ pdfPhase === 'generating' ? '正在生成并保存 PDF…' : ready ? '重新生成 PDF' : pdfPhase === 'failed' ? '重试生成 PDF' : '确认并生成 PDF' }}</button>
            <p class="hint">可随时用相同模板和内容重做 PDF，不调用模型；生成期间请勿关闭。修改内容或模板后需重新核对。</p>
          </div>
          <fieldset v-if="templates" class="stack template-picker">
            <legend>投递 PDF 模板</legend>
            <label v-for="item in templates.items" :key="item.id" class="template-option" :class="{ selected: templateId === item.id }">
              <input v-model="templateId" type="radio" name="resume-template" :value="item.id" @change="selectTemplate">
              <span class="template-preview">
                <img v-if="item.preview_url" :src="item.preview_url" :alt="`${item.name}样例`">
                <span v-else class="hint">预览图待补充</span>
              </span>
              <span><strong>{{ item.name }}</strong><span class="hint">{{ item.description }}</span></span>
            </label>
          </fieldset>
          <p class="hint">仅编辑本职位的简历，不覆盖全局底板。工作要点可增删和排序。</p>
          <ResumeEditor v-model="draft" @change="changed" />
        </fieldset></form>
        <details v-if="current"><summary>预览当前简历内容</summary><ResumePreview :profile="draft" /></details>
        <details v-if="current"><summary>对照生成时的底板快照</summary><pre class="prose">{{ JSON.stringify(current.source_resume, null, 2) }}</pre></details>
      </section>
    </div>
  </dialog>
</template>
