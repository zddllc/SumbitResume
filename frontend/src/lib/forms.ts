import { ref, onBeforeUnmount, type Ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { auth } from './auth'
import type { ResumeProfile, Message, Task } from '../types'

export const errorText = (error: unknown) => error instanceof Error ? error.message : '发生未知错误，请查看控制台'
export const dateText = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : ''
export const lines = (value: string) => value.split('\n').map(item => item.trim()).filter(Boolean)
export const activeTask = (task: Task) => ['queued', 'running', 'cancelling'].includes(task.status)
export function useUnsavedGuard(dirty: Ref<boolean>) {
  onBeforeRouteLeave(() => !auth.user || !dirty.value || window.confirm('表单有未保存修改，是否离开？'))
}
export function emptyResume(): ResumeProfile {
  return { contact: { name: '', email: '', phone: '', location: '', linkedin: '', website: '' }, summary: '', skills: [], experience: [], education: [], publications: [], projects: [], certifications: [], languages: [] }
}
export function useAction() {
  const busy = ref(false)
  const message = ref<Message | null>(null)
  async function run(work: () => Promise<void>, success?: string) {
    if (busy.value) return
    busy.value = true
    message.value = null
    try {
      await work()
      if (success) message.value = { text: success, kind: 'success' }
    } catch (error) {
      message.value = { text: errorText(error), kind: 'error' }
    } finally { busy.value = false }
  }
  return { busy, message, run }
}
export function usePolling(work: () => Promise<void>, enabled: () => boolean, fail: (error: unknown) => void, interval = 2500) {
  let running = false
  const timer = setInterval(async () => {
    if (running || !enabled()) return
    running = true
    try { await work() } catch (error) { fail(error) } finally { running = false }
  }, interval)
  onBeforeUnmount(() => clearInterval(timer))
}
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < 0 || from >= items.length || to >= items.length) throw new RangeError('移动条目索引超出范围')
  const result = [...items]
  const moved = result.splice(from, 1)
  result.splice(to, 0, ...moved)
  return result
}
