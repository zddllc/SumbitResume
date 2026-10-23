import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProfilePage from './ProfilePage.vue'
import { api } from '../lib/api'
import { emptyResume } from '../lib/forms'
import type { ResumeProfile, ResumeRecord, Task } from '../types'

vi.mock('../lib/api', async importOriginal => {
  const original = await importOriginal<typeof import('../lib/api')>()
  return { ...original, api: vi.fn() }
})

function records() {
  const profile = emptyResume()
  profile.contact = { ...profile.contact, name: 'Applicant', phone: '12345678' }
  profile.summary = 'Saved introduction'
  const record: ResumeRecord = { id: 'local', draft: profile, edit_token: 'saved-token' }
  const incoming = structuredClone(profile)
  incoming.summary = 'Uploaded introduction'
  const pending: ResumeRecord = { ...record, pending_import: { id: 'import-id', filename: 'new.docx', created_at: '2026-10-22T00:00:00Z', profile: incoming } }
  return { profile, record, pending }
}

async function mountPage(record: ResumeRecord, tasks: Task[] = []) {
  vi.mocked(api).mockResolvedValueOnce({ resume: record, tasks })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: ProfilePage }] })
  await router.push('/')
  const host = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), { global: { plugins: [router] } })
  await flushPromises()
  return host
}

describe('profile import integration', () => {
  afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

  it('loads a persisted comparison, explicitly applies it, then allows editing and confirming the saved draft', async () => {
    const { profile, pending } = records()
    const host = await mountPage(pending)
    expect(host.get('.resume-editor').element.closest('fieldset')?.disabled).toBe(true)
    await host.get('[data-import-field=summary] input[value=incoming]').setValue()
    const applied: ResumeRecord = { ...pending, draft: { ...profile, summary: 'Uploaded introduction' }, pending_import: null, edit_token: 'applied-token' }
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ resume: applied, tasks: [] })
    await host.get('.import-review form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('resume/import/apply', 'POST', {
      edit_token: 'saved-token', import_id: 'import-id', profile: applied.draft,
    })
    expect(host.find('.import-review').exists()).toBe(false)
    expect(host.get('.resume-editor').element.closest('fieldset')?.disabled).toBe(false)
    await host.get('.resume-editor > label textarea').setValue('Edited after applying')
    await host.get('.resume-editor [data-section=publications] .section-heading button').trigger('click')
    await host.get('[data-section=publications] input').setValue('Manually added paper')
    await host.get('[data-section=publications] .entry > button').trigger('click')
    await host.get('section.card form .check input').setValue(true)
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ resume: applied, tasks: [] })
    await host.get('section.card form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('resume/confirm', 'POST', expect.objectContaining({
      edit_token: 'applied-token', profile: expect.objectContaining({ summary: 'Edited after applying', publications: [] }),
    }))
    host.unmount()
  })

  it('keeps the comparison and selected choices visible when the server rejects a stale application', async () => {
    const { pending } = records()
    const host = await mountPage(pending)
    await host.get('[data-import-field=summary] input[value=incoming]').setValue()
    vi.mocked(api).mockRejectedValueOnce(new Error('底板或上传结果已更新，请重新加载后对比'))
    await host.get('.import-review form').trigger('submit')
    await flushPromises()
    expect(host.get('[role=alert]').text()).toContain('请重新加载后对比')
    expect((host.get('[data-import-field=summary] input[value=incoming]').element as HTMLInputElement).checked).toBe(true)
    expect((host.get('.resume-editor > label textarea').element as HTMLTextAreaElement).value).toBe('Saved introduction')
    host.unmount()
  })

  it('retains unsaved local edits when a parsing task finishes and compares against those edits', async () => {
    vi.useFakeTimers()
    const { profile, record, pending } = records()
    const task: Task = { id: 'parse', kind: 'parse', status: 'running', created_at: '', processed: 0, generated: 0, cached: 0, failed: 0, errors: [] }
    const host = await mountPage(record, [task])
    await host.get('.resume-editor > label textarea').setValue('Unsaved local introduction')
    vi.mocked(api).mockResolvedValueOnce({ resume: pending, tasks: [] })
    await vi.advanceTimersByTimeAsync(2500)
    await flushPromises()
    expect(host.get('[data-import-field=summary]').text()).toContain('Unsaved local introduction')
    const selected: ResumeProfile = { ...profile, summary: 'Unsaved local introduction' }
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ resume: { ...record, draft: selected, edit_token: 'applied-token' }, tasks: [] })
    await host.get('.import-review form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('resume/import/apply', 'POST', expect.objectContaining({ profile: selected }))
    host.unmount()
  })

  it('discards a pending upload without modifying the saved draft', async () => {
    const { record, pending } = records()
    const host = await mountPage(pending)
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ resume: record, tasks: [] })
    await host.get('.import-review button[type=button]').trigger('click')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('resume/import/discard', 'POST', { edit_token: 'saved-token', import_id: 'import-id' })
    expect(host.find('.import-review').exists()).toBe(false)
    expect((host.get('.resume-editor > label textarea').element as HTMLTextAreaElement).value).toBe('Saved introduction')
    host.unmount()
  })

  it('posts the exact selected field and point combination instead of replacing a complete work entry', async () => {
    const { record, pending } = records()
    record.draft!.experience = [{ company: 'Company', title: 'Engineer', location: 'Remote', start_date: '2020', end_date: '2024', bullets: ['Manual point', 'Old second point'] }]
    pending.pending_import!.profile.experience = [{
      ...record.draft!.experience[0]!, end_date: '2025', location: 'New office', bullets: ['New first point', 'New second point'],
    }]
    const host = await mountPage(pending)
    await host.get('[data-import-section=experience] [data-import-field=end_date] input[value=incoming]').setValue()
    await host.findAll('[data-import-list=bullets] [data-point-source=current] input')[1]!.setValue(false)
    await host.findAll('[data-import-list=bullets] [data-point-source=incoming] input')[1]!.setValue(true)
    const selected = {
      ...record.draft!, experience: [{
        ...record.draft!.experience[0]!, end_date: '2025', bullets: ['Manual point', 'New second point'],
      }],
    }
    vi.mocked(api).mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({
      resume: { ...record, draft: selected, edit_token: 'applied-token' }, tasks: [],
    })
    await host.get('.import-review form').trigger('submit')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('resume/import/apply', 'POST', {
      edit_token: 'saved-token', import_id: 'import-id', profile: selected,
    })
    expect(host.findAll('[data-section=experience] .entry')).toHaveLength(1)
    expect(host.get('[data-section=experience] .work-bullet-entry textarea').element).toHaveProperty('value', 'Manual point')
    host.unmount()
  })
})
