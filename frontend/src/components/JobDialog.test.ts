import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import JobDialog from './JobDialog.vue'
import { api } from '../lib/api'
import { emptyResume } from '../lib/forms'
import type { Job, LatestSource, PdfArtifact, TailoredResume, Task, TemplateCatalog } from '../types'

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

async function mountEditor(overrides: Partial<TailoredResume> = {}, templates: TemplateCatalog = catalog) {
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
  vi.mocked(api).mockResolvedValueOnce(templates).mockResolvedValueOnce({ job, versions: [loaded] }).mockResolvedValueOnce(loaded)
  const page = defineComponent({ components: { JobDialog }, template: '<JobDialog job-id="123" />' })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }] })
  await router.push('/')
  const host = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), { global: { plugins: [router] } })
  await flushPromises()
  return { host, loaded }
}

describe('job editor and PDF templates', () => {
  afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })
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

  it('renders the added 000 template from the catalog and submits that choice without changing the default', async () => {
    const templates: TemplateCatalog = {
      ...catalog, items: [...catalog.items, { id: 'serif-000', name: '衬线履历 · 000', description: '下划线标题', preview_url: null }],
    }
    const { host, loaded } = await mountEditor({}, templates)
    expect((host.get('input[value="classic-044"]').element as HTMLInputElement).checked).toBe(true)
    expect(host.findAll('.template-option')).toHaveLength(3)
    await host.get('input[value="serif-000"]').setValue()
    await host.get('form .check input').setValue(true)
    const saved = structuredClone(loaded)
    saved.template_id = 'serif-000'
    saved.pdf_ready = true
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce(saved)
    await host.get('form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('tailored/version/review', 'POST', expect.objectContaining({ template_id: 'serif-000' }))
    expect(host.find('a[download]').exists()).toBe(true)
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

  it('shows generating and completed states and permits repeated PDF generation with unchanged content and template', async () => {
    const { host, loaded } = await mountEditor()
    const artifact: PdfArtifact = { file_id: 'pdf-one', sha256: 'digest', profile_hash: 'profile', size: 200, created_at: '2026-10-23T00:00:00Z' }
    let finish: (value: object) => void = () => { throw new Error('Request not started') }
    vi.mocked(api).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await host.get('form .check input').setValue(true)
    await host.get('form').trigger('submit')
    expect(host.get('[data-pdf-status]').text()).toContain('正在制作 PDF')
    expect(host.get('form > fieldset').attributes('disabled')).toBeDefined()
    expect(host.find('a[download]').exists()).toBe(false)
    const saved: TailoredResume = { ...structuredClone(loaded), pdf_ready: true, pdf: artifact, edit_token: 'after-one', template_id: 'classic-044' }
    vi.mocked(api).mockResolvedValueOnce(saved)
    finish({ pdf: artifact })
    await flushPromises()
    expect(host.get('[data-pdf-status]').text()).toContain('PDF 已完成，可以下载')
    expect(host.get('a[download]').attributes('href')).toContain('v=pdf-one')
    expect(host.get('button[type=submit]').text()).toBe('重新生成 PDF')
    expect(host.get('button[type=submit]').attributes('disabled')).toBeUndefined()
    const again = { ...saved, pdf: { ...artifact, file_id: 'pdf-two' }, edit_token: 'after-two' }
    vi.mocked(api).mockResolvedValueOnce({ pdf: again.pdf }).mockResolvedValueOnce(again)
    await host.get('form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('tailored/version/review', 'POST', expect.objectContaining({ edit_token: 'after-one', template_id: 'classic-044' }))
    expect(host.get('a[download]').attributes('href')).toContain('v=pdf-two')
    host.unmount()
  })

  it('preserves edits and permits retry after a failed render without requiring a template change', async () => {
    const { host } = await mountEditor()
    await host.get('.resume-editor input').setValue('Unsaved Applicant')
    await host.get('form .check input').setValue(true)
    vi.mocked(api).mockRejectedValueOnce(new Error('Synthetic renderer failure'))
    await host.get('form').trigger('submit')
    await flushPromises()
    expect(host.get('[data-pdf-status]').text()).toContain('PDF 生成失败')
    expect(host.get('button[type=submit]').text()).toBe('重试生成 PDF')
    expect(host.get('button[type=submit]').attributes('disabled')).toBeUndefined()
    expect((host.get('.resume-editor input').element as HTMLInputElement).value).toBe('Unsaved Applicant')
    expect(host.find('a[download]').exists()).toBe(false)
    host.unmount()
  })

  it('does not claim a PDF is downloadable when the save succeeds but readiness verification fails', async () => {
    const { host } = await mountEditor({ pdf_ready: true })
    await host.get('form .check input').setValue(true)
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockRejectedValueOnce(new Error('Refresh offline'))
    await host.get('form').trigger('submit')
    await flushPromises()
    expect(host.get('[data-pdf-status]').text()).toContain('未能核验最新文件状态')
    expect(host.find('a[download]').exists()).toBe(false)
    expect(host.get('button[type=submit]').attributes('disabled')).toBeDefined()
    host.unmount()
  })

  it('detects base changes without resetting edits, then only fills blank fields from a freshly fetched confirmed source', async () => {
    vi.useFakeTimers()
    const source = emptyResume()
    source.contact.name = 'Source Applicant'
    source.contact.phone = '+1 555 0100'
    source.publications = [{ title: 'New paper', authors: ['Author'], venue: '', date: '', doi: '', url: '', details: [] }]
    const initial: LatestSource = { status: 'current', confirmed: source, confirmed_hash: 'first', has_pending_changes: false }
    const { host } = await mountEditor({ latest_source: initial })
    await host.get('.resume-editor input').setValue('Manual Applicant')
    const changed: LatestSource = { ...initial, status: 'changed', confirmed_hash: 'latest', has_pending_changes: true }
    vi.mocked(api).mockResolvedValueOnce(changed)
    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    expect(host.get('[data-source-status]').text()).toContain('底板已变化')
    expect(host.get('[data-source-status]').text()).toContain('未确认草稿')
    expect((host.get('.resume-editor input').element as HTMLInputElement).value).toBe('Manual Applicant')
    vi.mocked(api).mockResolvedValueOnce(changed)
    const button = host.findAll('button').find(item => item.text() === '仅补齐空白（不调用模型）')!
    await button.trigger('click')
    await flushPromises()
    expect((host.get('.resume-editor input').element as HTMLInputElement).value).toBe('Manual Applicant')
    expect((host.findAll('.resume-editor input')[2]!.element as HTMLInputElement).value).toBe('+1 555 0100')
    expect(host.findAll('[data-section=publications] .entry')).toHaveLength(1)
    expect(host.find('a[download]').exists()).toBe(false)
    expect(api).not.toHaveBeenCalledWith('jobs/123/generate', expect.anything(), expect.anything())
    host.unmount()
  })

  it('automatically loads the exact model task result even when a reused version is not the newest history item', async () => {
    vi.useFakeTimers()
    const { host, loaded } = await mountEditor()
    await host.get('.card .check input').setValue(true)
    const task: Task = { id: 'task', kind: 'tailor', status: 'running', created_at: '', processed: 0, generated: 0, cached: 0, failed: 0, errors: [] }
    vi.mocked(api).mockResolvedValueOnce({ task_id: 'task' }).mockResolvedValueOnce(task)
    await host.findAll('button').find(button => button.text() === '按最新已确认底板生成内容（模型）')!.trigger('click')
    await flushPromises()
    expect(host.get('form > fieldset').attributes('disabled')).toBeDefined()
    const reused: TailoredResume = { ...structuredClone(loaded), id: 'reused-old-version', edit_token: 'reused-token' }
    reused.resume.contact.name = 'Correct cached result'
    const done = { ...task, status: 'succeeded', cached: 1, result_resume_id: reused.id }
    vi.mocked(api).mockResolvedValueOnce(done).mockResolvedValueOnce({ job: loaded.job, versions: [loaded] }).mockResolvedValueOnce(reused)
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(api).toHaveBeenCalledWith('tailored/reused-old-version')
    expect((host.get('.resume-editor input').element as HTMLInputElement).value).toBe('Correct cached result')
    expect(host.text()).toContain('自动加载')
    expect((host.get('select').element as HTMLSelectElement).value).toBe('reused-old-version')
    host.unmount()
  })

  it('retries loading the exact completed task version after a refresh failure instead of guessing the newest history entry', async () => {
    const { host, loaded } = await mountEditor()
    await host.get('.card .check input').setValue(true)
    const done: Task = {
      id: 'task', kind: 'tailor', status: 'succeeded', created_at: '', processed: 1,
      generated: 0, cached: 1, failed: 0, errors: [], result_resume_id: 'cached-result',
    }
    vi.mocked(api).mockResolvedValueOnce({ task_id: 'task' }).mockResolvedValueOnce(done).mockRejectedValueOnce(new Error('History refresh offline'))
    await host.findAll('button').find(button => button.text() === '按最新已确认底板生成内容（模型）')!.trigger('click')
    await flushPromises()
    expect(host.get('[role=alert]').text()).toContain('History refresh offline')
    expect((host.get('.resume-editor input').element as HTMLInputElement).value).toBe('Loaded Applicant')
    const result = { ...structuredClone(loaded), id: 'cached-result' }
    result.resume.contact.name = 'Correct recovered version'
    vi.mocked(api).mockResolvedValueOnce({ job: loaded.job, versions: [loaded] }).mockResolvedValueOnce(result)
    await host.findAll('button').find(button => button.text() === '加载最新结果')!.trigger('click')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('tailored/cached-result')
    expect((host.get('.resume-editor input').element as HTMLInputElement).value).toBe('Correct recovered version')
    host.unmount()
  })
})
