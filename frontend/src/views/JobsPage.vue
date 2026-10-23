<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { activeTask, errorText, useAction, usePolling } from '../lib/forms'
import type { AppState, JobPage, Task } from '../types'
import NoticeBanner from '../components/NoticeBanner.vue'
import TaskList from '../components/TaskList.vue'
import JobDialog from '../components/JobDialog.vue'

const state = ref<AppState | null>(null), jobs = ref<JobPage>({ items: [], page: 1, total: 0 })
const tasks = ref<Task[]>([]), page = ref(1), limit = ref(20), consent = ref(false)
const selected = ref<string | null>(null)
const { busy, message, run } = useAction()
const pages = computed(() => Math.max(1, Math.ceil(jobs.value.total / 25)))
async function loadJobs() { jobs.value = await api<JobPage>(`jobs?page=${page.value}`) }
async function loadTasks() {
  const previous = new Map(tasks.value.map(task => [task.id, task.status]))
  tasks.value = (await api<{ items: Task[] }>('tasks')).items
  if (tasks.value.some(task => ['queued', 'running', 'cancelling'].includes(previous.get(task.id) || '') && !activeTask(task))) await loadJobs()
}
async function load() {
  state.value = await api<AppState>('state')
  tasks.value = state.value.tasks
  await loadJobs()
}
onMounted(() => run(load))
usePolling(loadTasks, () => tasks.value.some(activeTask), error => { message.value = { text: errorText(error), kind: 'error' } })
async function openBrowser() { await run(async () => { await api('browser/open', 'POST'); await loadTasks() }, '已安排打开 Chrome，请在后端机器的图形桌面手动登录 LinkedIn。') }
async function scan() {
  await run(async () => {
    if (!consent.value) throw new Error('请先确认模型调用授权')
    if (!Number.isInteger(limit.value) || limit.value < 1 || limit.value > 100) throw new Error('职位上限必须是 1–100 的整数')
    await api('jobs/scan', 'POST', { limit: limit.value, consent: true })
    await loadTasks(); await loadJobs()
  }, '遍历任务已开始。请不要关闭后端 Chrome。')
}
async function cancel(id: string) { await run(async () => { await api(`tasks/${id}/cancel`, 'POST'); await loadTasks() }) }
async function changePage(offset: number) { await run(async () => { page.value += offset; await loadJobs() }) }
async function changed() { await run(async () => { await loadJobs(); await loadTasks() }) }
</script>
<template>
  <header class="page-heading"><div><span class="eyebrow">WORKSPACE</span><h1>把每个机会，变成专属简历。</h1><p class="muted">你负责确认事实与登录，工作台负责整理和保存。</p></div><span class="pill">单用户 · 后端浏览器</span></header>
  <NoticeBanner :message="message" />
  <div class="setup-strip">
    <span class="readiness" :class="{ ready: state?.llm.key_saved }">{{ state?.llm.key_saved ? '已就绪' : '待设置' }} · 模型连接</span>
    <span class="readiness" :class="{ ready: state?.resume?.confirmed }">{{ state?.resume?.confirmed ? '已就绪' : '待设置' }} · 简历底板</span>
  </div>
  <div class="two-column">
    <article class="card"><span class="step-number">01 / CONNECT</span><h2>登录 LinkedIn</h2><p>Chrome 打开在运行后端的机器上。部署到 113 后，请进入 113 的 Linux 桌面完成登录和安全验证。</p><button :disabled="busy" @click="openBrowser">打开受控 Chrome</button><p class="hint">登录状态保存在后端独立目录，不读取访问者电脑的 Chrome 配置。</p></article>
    <article class="card"><span class="step-number">02 / DISCOVER &amp; TAILOR</span><h2>遍历推荐职位</h2>
      <label>单次职位上限（1–100）<input v-model.number="limit" type="number" min="1" max="100"></label>
      <label class="check"><input v-model="consent" type="checkbox">同意把已确认底板和职位描述发给配置的模型服务，并保存请求和响应用于审核。</label>
      <button :disabled="busy" @click="scan">开始遍历与定制</button><p class="hint">会产生模型费用。外站入口采集可能打开临时标签页；不填写、不提交申请。</p>
    </article>
  </div>
  <section class="card"><div class="section-heading"><h2>后台任务</h2><span class="hint">取消在当前浏览器 / API 操作结束后生效</span></div><TaskList :tasks="tasks" :disabled="busy" @cancel="cancel" /></section>
  <section class="card">
    <div class="section-heading"><div><h2>职位与定制简历</h2><p class="hint">已保存 {{ jobs.total }} 个职位</p></div><button class="secondary small" :disabled="busy" @click="run(loadJobs)">刷新</button></div>
    <p v-if="!jobs.items.length" class="empty">暂无职位。确认底板并登录 LinkedIn 后，开始第一次遍历。</p>
    <article v-for="job in jobs.items" :key="job.id" class="job-row">
      <div><h3>{{ job.title }}</h3><p class="hint">{{ [job.company, job.location].filter(Boolean).join(' · ') }}</p>
        <span class="badge">{{ !job.tailored ? '描述已保存，尚未生成简历' : !job.current_source ? '历史简历 · 底板或职位已变化' : job.tailored.review_status === 'reviewed' && job.tailored.pdf ? '已确认 · PDF 已生成' : '已生成 · 待编辑确认 PDF' }}</span>
      </div>
      <button class="secondary small" @click="selected = job.linkedin_id">查看职位与简历</button>
    </article>
    <div class="pagination"><button class="secondary small" :disabled="busy || page === 1" @click="changePage(-1)">上一页</button><span>{{ page }} / {{ pages }}</span><button class="secondary small" :disabled="busy || page >= pages" @click="changePage(1)">下一页</button></div>
  </section>
  <JobDialog v-if="selected" :job-id="selected" @close="selected = null" @changed="changed" />
</template>
