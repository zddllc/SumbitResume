import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { emptyResume } from '../lib/forms'
import ResumePreview from './ResumePreview.vue'

describe('publication preview', () => {
  it('folds publications by default and reveals citation metadata without rendering user markup', async () => {
    const profile = emptyResume()
    profile.publications = [{
      title: '<script>Paper title</script>', authors: ['First Author', 'Second Author'],
      venue: 'Conference', date: '2025', doi: '10.1234/paper',
      url: 'https://example.org/paper', details: ['Pages 1-8'],
    }]
    const wrapper = mount(ResumePreview, { props: { profile } })
    expect((wrapper.get('[data-preview-section=publications]').element as HTMLDetailsElement).open).toBe(false)
    await wrapper.get('[data-preview-section=publications] summary').trigger('click')
    expect((wrapper.get('[data-preview-section=publications]').element as HTMLDetailsElement).open).toBe(true)
    const text = wrapper.text()
    for (const value of ['论文 / Publications', '<script>Paper title</script>', 'Conference', '2025', 'DOI: 10.1234/paper', 'https://example.org/paper', 'Pages 1-8']) expect(text).toContain(value)
    expect(text.indexOf('First Author')).toBeLessThan(text.indexOf('Second Author'))
    expect(wrapper.find('script').exists()).toBe(false)
    wrapper.unmount()
  })
})
