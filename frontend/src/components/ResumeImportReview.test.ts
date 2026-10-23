import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { emptyResume } from '../lib/forms'
import ResumeImportReview from './ResumeImportReview.vue'

function review() {
  const current = emptyResume()
  current.contact = { ...current.contact, name: 'Applicant', phone: '12345678' }
  current.summary = 'Existing introduction'
  current.experience = [{ company: 'Company', title: 'Engineer', location: 'Remote', start_date: '2020', end_date: '2024', bullets: ['Manual first point', 'Second point', 'Shared point'] }]
  const incoming = structuredClone(current)
  incoming.summary = 'New introduction'
  incoming.experience[0]!.bullets = ['New work entry', 'Shared point']
  incoming.experience[0]!.location = 'New office'
  incoming.experience[0]!.end_date = '2025'
  incoming.publications = [{ title: '<script>New paper</script>', authors: ['First Author', 'Second Author'], venue: 'Conference', date: '2025', doi: '', url: '', details: [] }]
  const wrapper = mount(ResumeImportReview, { props: { current, incoming, filename: 'new.docx', disabled: false } })
  return { wrapper, current, incoming }
}

describe('field-level upload comparison', () => {
  it('hides identical contacts and shows readable old/new choices without executing markup', () => {
    const { wrapper } = review()
    expect(wrapper.find('[data-import-field=name]').exists()).toBe(false)
    expect(wrapper.find('[data-import-field=phone]').exists()).toBe(false)
    expect(wrapper.get('[data-import-field=summary]').text()).toContain('Existing introduction')
    expect(wrapper.get('[data-import-section=experience]').text()).toContain('Manual first point')
    expect(wrapper.get('[data-import-section=experience]').text()).toContain('New work entry')
    expect(wrapper.find('[data-import-section=experience] [data-import-field=company]').exists()).toBe(false)
    expect(wrapper.find('[data-import-section=experience] [data-import-field=title]').exists()).toBe(false)
    expect(wrapper.findAll('[data-point-source=both]')).toHaveLength(1)
    expect(wrapper.get('[data-import-section=publications]').text()).toContain('<script>New paper</script>')
    expect(wrapper.find('script').exists()).toBe(false)
    wrapper.unmount()
  })

  it('mixes selected fields and individual work points in one entry and can omit a new paper', async () => {
    const { wrapper, current, incoming } = review()
    await wrapper.get('[data-import-field=summary] input[value=incoming]').setValue()
    await wrapper.get('[data-import-section=experience] [data-import-field=end_date] input[value=incoming]').setValue()
    await wrapper.findAll('[data-import-list=bullets] [data-point-source=current] input')[1]!.setValue(false)
    await wrapper.get('[data-import-list=bullets] [data-point-source=incoming] input').setValue(true)
    await wrapper.get('[data-import-section=publications] [data-new-entry] input').setValue(false)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('apply')?.[0]?.[0]).toEqual({
      ...current, summary: incoming.summary, experience: [{
        ...current.experience[0], end_date: '2025', bullets: ['Manual first point', 'Shared point', 'New work entry'],
      }],
    })
    expect(wrapper.emitted('change')).toHaveLength(5)
    expect(current.summary).toBe('Existing introduction')
    wrapper.unmount()
  })

  it('defaults to keeping old work points while new points require explicit selection', () => {
    const { wrapper } = review()
    for (const input of wrapper.findAll('[data-import-list=bullets] [data-point-source=current] input, [data-import-list=bullets] [data-point-source=both] input')) {
      expect((input.element as HTMLInputElement).checked).toBe(true)
    }
    expect((wrapper.get('[data-import-list=bullets] [data-point-source=incoming] input').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.find('[data-import-section=experience] input[value=both]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers an ordered author field separately from other paper facts', async () => {
    const current = emptyResume()
    current.publications = [{ title: 'Paper', authors: ['First', 'Second'], venue: 'Old venue', date: '2024', doi: '', url: '', details: [] }]
    const incoming = structuredClone(current)
    incoming.publications[0]!.authors.reverse()
    incoming.publications[0]!.venue = 'New venue'
    const wrapper = mount(ResumeImportReview, { props: { current, incoming, filename: 'paper.docx', disabled: false } })
    expect(wrapper.get('[data-import-field=authors]').text()).toContain('不拼接或重排作者')
    expect(wrapper.find('[data-import-list=authors]').exists()).toBe(false)
    await wrapper.get('[data-import-field=venue] input[value=incoming]').setValue()
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('apply')?.[0]?.[0]).toEqual({
      ...current, publications: [{ ...current.publications[0], venue: 'New venue' }],
    })
    wrapper.unmount()
  })

  it('discards without emitting an application and disables choices while saving', async () => {
    const { wrapper } = review()
    await wrapper.get('button[type=button]').trigger('click')
    expect(wrapper.emitted('discard')).toHaveLength(1)
    expect(wrapper.emitted('apply')).toBeUndefined()
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('folds all secondary comparison modules without losing selections or marking a fold as an edit', async () => {
    const current = emptyResume()
    current.contact.name = 'Applicant'
    const incoming = structuredClone(current)
    incoming.education = [{ institution: 'University', degree: 'BSc', field: '', start_date: '', end_date: '', details: [] }]
    incoming.publications = [{ title: 'Paper', authors: ['Author'], venue: '', date: '', doi: '', url: '', details: [] }]
    incoming.projects = [{ name: 'Project', url: '', bullets: [] }]
    incoming.certifications = [{ name: 'Certificate', issuer: '', date: '' }]
    incoming.languages = [{ name: 'English', proficiency: 'Fluent' }]
    const wrapper = mount(ResumeImportReview, { props: { current, incoming, filename: 'new.docx', disabled: false } })
    for (const key of ['education', 'publications', 'projects', 'certifications', 'languages']) {
      const section = wrapper.get(`[data-import-section=${key}]`)
      expect((section.element as HTMLDetailsElement).open).toBe(false)
      expect(section.get('summary').text()).toContain('1 项')
    }
    const papers = wrapper.get('[data-import-section=publications]')
    await papers.get('summary').trigger('click')
    expect(wrapper.emitted('change')).toBeUndefined()
    await papers.get('[data-new-entry] input').setValue(false)
    await papers.get('summary').trigger('click')
    await papers.get('summary').trigger('click')
    expect((papers.get('[data-new-entry] input').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.emitted('change')).toHaveLength(1)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('apply')?.[0]?.[0]).toEqual({ ...incoming, publications: [] })
    wrapper.unmount()
  })
})
