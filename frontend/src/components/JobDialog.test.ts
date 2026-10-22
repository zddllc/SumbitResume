import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import JobDialog from './JobDialog.vue'
import { api } from '../lib/api'
import { emptyResume } from '../lib/forms'
import type { Job, TailoredResume } from '../types'

vi.mock('../lib/api', async importOriginal => {
  const original = await importOriginal<typeof import('../lib/api')>()
  return { ...original, api: vi.fn() }
})

describe('job editor data isolation', () => {
  afterEach(() => vi.clearAllMocks())
  it('clones plain API data before Vue wraps it and keeps editing separate from the loaded record', async () => {
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
      configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') },
    })
    Object.defineProperty(HTMLDialogElement.prototype, 'close', {
      configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') },
    })
    const profile = emptyResume()
    profile.contact.name = 'Loaded Applicant'
    profile.experience = [{ company: 'Example', title: 'Engineer', location: '', start_date: '', end_date: '', bullets: ['Source point'] }]
    const job: Job & { description: string } = {
      id: 'local:123', linkedin_id: '123', url: 'https://www.linkedin.com/jobs/view/123/',
      title: 'Sample Role', company: 'Example', location: 'Remote', description: 'Sample description for a role.',
    }
    const loaded: TailoredResume = {
      id: 'version', created_at: '2026-10-22T00:00:00Z', llm: { model: 'test' },
      review_status: 'pending', job, resume: profile, source_resume: structuredClone(profile),
      edit_token: 'token', application: { kind: 'unavailable' }, pdf_ready: false,
    }
    vi.mocked(api).mockResolvedValueOnce({ job, versions: [loaded] }).mockResolvedValueOnce(loaded)
    const page = defineComponent({ components: { JobDialog }, template: '<JobDialog job-id="123" />' })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }] })
    await router.push('/')
    const host = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), { global: { plugins: [router] } })
    await flushPromises()
    expect(host.find('[role=alert]').exists()).toBe(false)
    const name = host.find('.resume-editor input')
    expect((name.element as HTMLInputElement).value).toBe('Loaded Applicant')
    await name.setValue('Edited Applicant')
    expect(loaded.resume.contact.name).toBe('Loaded Applicant')
    expect((host.find('.work-bullet-entry textarea').element as HTMLTextAreaElement).value).toBe('Source point')
    host.unmount()
  })
})
