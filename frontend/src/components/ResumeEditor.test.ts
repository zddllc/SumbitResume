import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResumeEditor from './ResumeEditor.vue'
import { emptyResume } from '../lib/forms'

function editor() {
  const profile = ref(emptyResume())
  profile.value.contact.name = 'Sample Applicant'
  profile.value.experience = [
    { company: 'First Co', title: 'Engineer', location: '', start_date: '', end_date: '', bullets: ['First\ncontinued', 'Second'] },
    { company: 'Other Co', title: 'Earlier Role', location: '', start_date: '', end_date: '', bullets: ['Other job'] },
  ]
  const host = mount(defineComponent({
    components: { ResumeEditor },
    setup: () => ({ profile }),
    template: '<ResumeEditor v-model="profile" />',
  }))
  return { host, profile }
}

describe('shared base and tailored editor', () => {
  it('edits, moves, adds and removes independent work points without touching another job', async () => {
    const { host, profile } = editor()
    const first = host.find('[data-section=experience] .entry')
    expect(first.find('[data-move=up]').attributes('disabled')).toBeDefined()
    expect(first.findAll('[data-move=down]')[1]!.attributes('disabled')).toBeDefined()
    await first.findAll('.work-bullet-entry textarea')[0]!.setValue('Edited\nsame entry')
    await first.find('[data-move=down]').trigger('click')
    expect(profile.value.experience[0]!.bullets).toEqual(['Second', 'Edited\nsame entry'])
    await first.find('.work-bullets .section-heading button').trigger('click')
    await first.findAll('.work-bullet-entry textarea')[2]!.setValue('Added point')
    await first.findAll('button[aria-label^="删除工作要点"]')[0]!.trigger('click')
    expect(profile.value.experience[0]!.bullets).toEqual(['Edited\nsame entry', 'Added point'])
    expect(profile.value.experience[1]!.bullets).toEqual(['Other job'])
    host.unmount()
  })
  it('revalidates textarea values when a point moves to a reused DOM row', async () => {
    const { host } = editor()
    const first = host.find('[data-section=experience] .entry')
    await first.findAll('textarea')[1]!.setValue('   ')
    await first.findAll('[data-move=up]')[1]!.trigger('click')
    await nextTick()
    const fields = first.findAll('textarea')
    expect((fields[0]!.element as HTMLTextAreaElement).validationMessage).not.toBe('')
    expect((fields[1]!.element as HTMLTextAreaElement).validationMessage).toBe('')
    host.unmount()
  })
  it('preserves the existing fifty-point limit and re-enables add after delete', async () => {
    const { host, profile } = editor()
    profile.value.experience[0]!.bullets = Array.from({ length: 50 }, (_, index) => `Point ${index}`)
    await nextTick()
    const first = host.find('[data-section=experience] .entry')
    expect(first.find('.work-bullets .section-heading button').attributes('disabled')).toBeDefined()
    await first.find('button[aria-label^="删除工作要点"]').trigger('click')
    expect(profile.value.experience[0]!.bullets).toHaveLength(49)
    expect(first.find('.work-bullets .section-heading button').attributes('disabled')).toBeUndefined()
    host.unmount()
  })
  it('adds, edits and removes publication entries without mixing them into projects', async () => {
    const { host, profile } = editor()
    const papers = host.find('[data-section=publications]')
    await papers.find('.section-heading button').trigger('click')
    expect((papers.element as HTMLDetailsElement).open).toBe(true)
    const inputs = papers.findAll('input')
    const areas = papers.findAll('textarea')
    await inputs[0]!.setValue('Paper title')
    await areas[0]!.setValue('First Author\nSecond Author')
    await inputs[1]!.setValue('Sample Conference')
    await inputs[2]!.setValue('2025')
    await inputs[3]!.setValue('10.1234/paper')
    await inputs[4]!.setValue('https://example.org/paper')
    await areas[1]!.setValue('Volume 2, pages 1-8\nEqual contribution')
    expect(profile.value.publications).toEqual([{
      title: 'Paper title', authors: ['First Author', 'Second Author'],
      venue: 'Sample Conference', date: '2025', doi: '10.1234/paper',
      url: 'https://example.org/paper', details: ['Volume 2, pages 1-8', 'Equal contribution'],
    }])
    expect(profile.value.projects).toEqual([])
    await papers.find('.entry > button').trigger('click')
    expect(profile.value.publications).toEqual([])
    host.unmount()
  })

  it('starts secondary modules collapsed, keeps work visible and retains edits when folded', async () => {
    const { host, profile } = editor()
    for (const key of ['education', 'publications', 'projects', 'certifications', 'languages']) {
      const section = host.get(`[data-section=${key}]`)
      expect(section.element.tagName).toBe('DETAILS')
      expect((section.element as HTMLDetailsElement).open).toBe(false)
      expect(section.get('summary').text()).toContain('0 项')
    }
    expect((host.get('[data-section=experience]').element as HTMLDetailsElement).open).toBe(true)
    const papers = host.get('[data-section=publications]')
    await papers.get('summary').trigger('click')
    await papers.get('.section-heading button').trigger('click')
    await papers.get('input').setValue('Saved paper title')
    await papers.get('summary').trigger('click')
    await host.get('.resume-editor input').setValue('Changed applicant')
    expect((papers.element as HTMLDetailsElement).open).toBe(false)
    expect(papers.get('summary').text()).toContain('1 项')
    await papers.get('summary').trigger('click')
    expect((papers.get('input').element as HTMLInputElement).value).toBe('Saved paper title')
    expect(profile.value.publications[0]!.title).toBe('Saved paper title')
    host.unmount()
  })
})
