import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import JobDialog from './JobDialog.vue'
import { api } from '../lib/api'
import { emptyResume } from '../lib/forms'
import type { Job, TailoredResume, TemplateCatalog } from '../types'

vi.mock('../lib/api', async importOriginal => {
  const original = await importOriginal<typeof import('../lib/api')>()
  return { ...original, api: vi.fn() }
})

const catalog: TemplateCatalog = {
  default_template_id: 'classic-044',
  items: [
    { id: 'classic-044', name: '经典灰条 · 044', description: '代码模板', preview_url: null },
    { id: 'simple', name: '简洁单栏', description: '原有模板', preview_url: null },
  ],
}

async function mountEditor(overrides: Partial<TailoredResume> = {}) {
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
    edit_token: 'token', application: { kind: 'unavailable' }, pdf_ready: false, ...overrides,
  }
  vi.mocked(api).mockResolvedValueOnce(catalog).mockResolvedValueOnce({ job, versions: [loaded] }).mockResolvedValueOnce(loaded)
  const page = defineComponent({ components: { JobDialog }, template: '<JobDialog job-id="123" />' })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }] })
  await router.push('/')
  const host = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), { global: { plugins: [router] } })
  await flushPromises()
  return { host, loaded }
}

describe('job editor and PDF templates', () => {
  afterEach(() => vi.clearAllMocks())
  it('clones plain API data before Vue wraps it and keeps editing separate from the loaded record', async () => {
    const { host, loaded } = await mountEditor()
    expect(host.find('[role=alert]').exists()).toBe(false)
    const name = host.find('.resume-editor input')
    expect((name.element as HTMLInputElement).value).toBe('Loaded Applicant')
    await name.setValue('Edited Applicant')
    expect(loaded.resume.contact.name).toBe('Loaded Applicant')
    expect((host.find('.work-bullet-entry textarea').element as HTMLTextAreaElement).value).toBe('Source point')
    host.unmount()
  })

  it('selects the backend default and leaves preview images empty', async () => {
    const { host } = await mountEditor()
    expect((host.get('input[value="classic-044"]').element as HTMLInputElement).checked).toBe(true)
    expect(host.findAll('.template-preview img')).toHaveLength(0)
    expect(host.findAll('.template-preview')).toHaveLength(2)
    expect(host.text()).not.toContain('模板已更换')
    host.unmount()
  })

  it('invalidates confirmation and hides the previous PDF when changing only the template', async () => {
    const { host } = await mountEditor({ pdf_ready: true, review_status: 'reviewed', template_id: 'simple' })
    expect(host.find('a[download]').exists()).toBe(true)
    await host.get('form .check input').setValue(true)
    await host.get('input[value="classic-044"]').setValue()
    expect(host.find('a[download]').exists()).toBe(false)
    expect(host.text()).toContain('模板已更换')
    expect((host.get('form .check input').element as HTMLInputElement).checked).toBe(false)
    expect(host.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    host.unmount()
  })

  it('posts the selected template with the latest edited profile and restores saved download links', async () => {
    const { host, loaded } = await mountEditor()
    await host.get('.resume-editor input').setValue('Latest Applicant')
    await host.get('input[value="simple"]').setValue()
    await host.get('form .check input').setValue(true)
    const saved = structuredClone(loaded)
    saved.template_id = 'simple'
    saved.resume.contact.name = 'Latest Applicant'
    saved.pdf_ready = true
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce(saved)
    await host.get('form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('tailored/version/review', 'POST', expect.objectContaining({
      confirmed: true, edit_token: 'token', template_id: 'simple',
      profile: expect.objectContaining({ contact: expect.objectContaining({ name: 'Latest Applicant' }) }),
    }))
    expect(host.find('a[download]').exists()).toBe(true)
    host.unmount()
  })

  it('keeps legacy confirmed PDFs on the simple template without forcing regeneration', async () => {
    const { host } = await mountEditor({ pdf_ready: true, review_status: 'reviewed' })
    expect((host.get('input[value="simple"]').element as HTMLInputElement).checked).toBe(true)
    expect(host.find('a[download]').exists()).toBe(true)
    host.unmount()
  })

  it('surfaces conversion failure without exposing old bytes as the newly selected template', async () => {
    const { host } = await mountEditor({ pdf_ready: true, template_id: 'simple' })
    await host.get('input[value="classic-044"]').setValue()
    await host.get('form .check input').setValue(true)
    vi.mocked(api).mockRejectedValueOnce(new Error('Office conversion failed'))
    await host.get('form').trigger('submit')
    await flushPromises()
    expect(host.get('[role="alert"]').text()).toContain('Office conversion failed')
    expect(host.find('a[download]').exists()).toBe(false)
    host.unmount()
  })
})
