<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api, apiUrl } from '../lib/api'
import { auth } from '../lib/auth'
import { activeTask, dateText, emptyResume, errorText, useAction, usePolling } from '../lib/forms'
import type { ApplicationInfo, JobDetail, ResumeProfile, TailoredResume, Task } from '../types'
import ResumeEditor from './ResumeEditor.vue'
import ResumePreview from './ResumePreview.vue'
import NoticeBanner from './NoticeBanner.vue'

const props = defineProps<{ jobId: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const info = ref<JobDetail | null>(null), current = ref<TailoredResume | null>(null)
const draft = ref<ResumeProfile>(emptyResume()), versionId = ref(''), dirty = ref(false), facts = ref(false)
const consent = ref(false), generationId = ref(''), generation = ref<Task | null>(null)
const { busy, message, run } = useAction()
const ready = computed(() => Boolean(current.value?.pdf_ready && !dirty.value))
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
function changed() { dirty.value = true; facts.value = false }
function canDiscard() { return !dirty.value || window.confirm('这份职位简历的修改尚未保存，是否丢弃？') }
function close() { if (!busy.value && canDiscard()) emit('close') }
function cancel(event: Event) { event.preventDefault(); close() }
onBeforeRouteLeave(() => {
  if (!auth.user) return true
  if (busy.value) {
    message.value = { text: '请求仍在进行，请稍候再离开。', kind: 'info' }
    return false
  }
  return canDiscard()
})
async function version(id: string) {
  const loaded = await api<TailoredResume>(`tailored/${encodeURIComponent(id)}`)
  const editable = structuredClone(loaded.resume)
  current.value = loaded
  versionId.value = id
  draft.value = editable
  dirty.value = false; facts.value = false
}
async function load() {
  info.value = await api<JobDetail>(`jobs/${encodeURIComponent(props.jobId)}`)
  const latest = info.value.versions[0]
  if (latest) await version(latest.id)
  else { current.value = null; versionId.value = ''; dirty.value = false }
}
onMounted(async () => { dialog.value?.showModal(); await run(load) })
onBeforeUnmount(() => dialog.value?.close())
async function selectVersion(event: Event) {
  if (!(event.target instanceof HTMLSelectElement)) throw new Error('版本控件异常')
  const id = event.target.value
  if (!canDiscard()) { event.target.value = versionId.value; return }
  await run(() => version(id))
}
async function reload() { if (canDiscard()) await run(load) }
async function confirm() {
  await run(async () => {
    if (!current.value || !facts.value) throw new Error('请核对后确认')
    await api(`tailored/${current.value.id}/review`, 'POST', {
      confirmed: true, edit_token: current.value.edit_token, profile: draft.value,
    })
    dirty.value = false
    try { await version(current.value.id) } catch { throw new Error('确认已保存，但界面刷新失败，请加载最新结果。') }
    emit('changed')
  }, '职位简历已确认，投递 PDF 已生成并保存。')
}
async function generate() {
  await run(async () => {
    if (!consent.value) throw new Error('请先确认模型调用授权')
    if (dirty.value) throw new Error('请先保存或放弃当前简历修改')
    const result = await api<{ task_id: string }>(`jobs/${encodeURIComponent(props.jobId)}/generate`, 'POST', { consent: true })
    generationId.value = result.task_id
    generation.value = await api<Task>(`tasks/${result.task_id}`)
    emit('changed')
  })
}
usePolling(async () => {
  generation.value = await api<Task>(`tasks/${generationId.value}`)
  if (!activeTask(generation.value)) emit('changed')
}, () => Boolean(generationId.value && (!generation.value || activeTask(generation.value))), error => { message.value = { text: errorText(error), kind: 'error' } })
</script>
<template>
  <dialog ref="dialog" @cancel="cancel">
    <div class="section-heading"><h2>{{ job?.title || '职位详情' }}</h2><button type="button" class="secondary small" :disabled="busy" @click="close">关闭</button></div>
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
          <p class="hint">使用已保存的描述和当前全局底板生成，无需重新访问 LinkedIn；相同输入直接复用。</p>
          <label class="check"><input v-model="consent" type="checkbox" :disabled="busy">同意把已保存的描述和已确认底板发给配置的模型服务，可能产生费用。</label>
          <div class="button-row"><button type="button" class="secondary" :disabled="busy || dirty" @click="generate">按当前底板生成本职位简历</button><button type="button" class="secondary" :disabled="busy" @click="reload">加载最新结果</button></div>
          <p v-if="generation" class="hint" role="status">{{ generation.status === 'succeeded' ? `生成任务已完成（新生成 ${generation.generated}，复用 ${generation.cached}）。点击“加载最新结果”查看。` : generation.error || `生成任务：${generation.status}` }}</p>
        </div>
        <label>历史版本<select :value="versionId" :disabled="busy" @change="selectVersion"><option v-for="item in info.versions" :key="item.id" :value="item.id">{{ dateText(item.created_at) }} · {{ item.llm.model }}</option></select></label>
        <p class="notice" :class="{ warning: !ready }">{{ dirty ? '有未保存修改，确认后生成新 PDF；不会修改全局底板。' : ready ? `已确认并保存 PDF · ${dateText(current?.reviewed_at)}` : current ? '请逐项核对并修改，确认后生成投递 PDF。模型可能误写事实。' : '职位已保存，尚无定制简历。可使用已存描述生成。' }}</p>
        <div v-if="ready && current" class="button-row">
          <a class="button secondary" :href="apiUrl(`tailored/${current.id}/pdf`)" target="_blank" rel="noopener noreferrer">查看已确认 PDF</a>
          <a class="button" :href="apiUrl(`tailored/${current.id}/pdf?download=1`)" download>下载投递 PDF</a>
        </div>
        <form v-if="current" @submit.prevent="confirm"><fieldset :disabled="busy" class="stack">
          <p class="hint">仅编辑本职位的简历，不覆盖全局底板。工作要点可增删和排序。</p>
          <ResumeEditor v-model="draft" @change="changed" />
          <label class="check"><input v-model="facts" type="checkbox" required>我已核对这份职位简历真实、准确，同意生成用于后续投递的 PDF。</label>
          <button type="submit" :disabled="!facts || ready">确认并生成 PDF</button>
        </fieldset></form>
        <details v-if="current"><summary>预览当前简历内容</summary><ResumePreview :profile="draft" /></details>
        <details v-if="current"><summary>对照生成时的底板快照</summary><pre class="prose">{{ JSON.stringify(current.source_resume, null, 2) }}</pre></details>
      </section>
    </div>
  </dialog>
</template>
