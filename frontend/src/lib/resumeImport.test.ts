import { describe, expect, it } from 'vitest'
import { emptyResume } from './forms'
import { applyImportPlan, createImportPlan, fillResumeGaps } from './resumeImport'
import type { ResumeProfile } from '../types'

function profile(): ResumeProfile {
  const value = emptyResume()
  value.contact = { ...value.contact, name: 'Applicant', phone: '12345678' }
  value.summary = 'Hand-written introduction.'
  value.skills = ['Python', 'SQL']
  value.experience = [{ company: 'Company', title: 'Engineer', location: 'Remote', start_date: '2020', end_date: '2024', bullets: ['Most important', 'Earlier point'] }]
  value.education = [{ institution: 'University', degree: 'BSc', field: 'CS', start_date: '2016', end_date: '2020', details: ['Original detail'] }]
  value.projects = [{ name: 'Project', url: 'https://example.test/project', bullets: ['Original contribution'] }]
  value.publications = [{ title: 'Paper', authors: ['First Author', 'Second Author'], venue: 'Conference', date: '2024', doi: '10.1234/paper', url: '', details: ['Pages 1-8'] }]
  value.certifications = [{ name: 'Certificate', issuer: 'Issuer', date: '2024' }]
  value.languages = [{ name: 'English', proficiency: 'Fluent' }]
  return value
}

describe('non-destructive resume import choices', () => {
  it('hides identical values in every section and preserves the existing order', () => {
    const original = profile()
    const incoming = structuredClone(original)
    incoming.summary = '  Hand-written   introduction. '
    incoming.skills.reverse()
    const plan = createImportPlan(original, incoming)
    expect(plan.scalars).toEqual([])
    for (const key of ['skills', 'experience', 'education', 'projects', 'publications', 'certifications', 'languages'] as const) {
      expect(plan[key].filter(item => item.changed)).toEqual([])
    }
    expect(applyImportPlan(plan)).toEqual(original)
  })

  it('never clears old fields or removes entries because the uploaded document omitted them', () => {
    const original = profile()
    const plan = createImportPlan(original, emptyResume())
    expect(plan.scalars).toEqual([])
    expect(applyImportPlan(plan)).toEqual(original)
  })

  it('keeps old scalar values by default and supports explicit selection of a whole introduction', () => {
    const original = profile()
    const incoming = structuredClone(original)
    incoming.summary = 'New introduction.'
    incoming.contact.phone = '87654321'
    const plan = createImportPlan(original, incoming)
    expect(plan.scalars.map(item => item.key)).toEqual(['phone', 'summary'])
    expect(applyImportPlan(plan)).toEqual(original)
    plan.scalars[0]!.choice = 'incoming'
    plan.scalars[1]!.choice = 'both'
    expect(applyImportPlan(plan).contact.phone).toBe('87654321')
    expect(applyImportPlan(plan).summary).toBe('Hand-written introduction.\n\nNew introduction.')
    plan.scalars[1]!.choice = 'incoming'
    expect(applyImportPlan(plan).summary).toBe('New introduction.')
    expect(original).toEqual(profile())
  })

  it('chooses individual work fields and points without overwriting hand-edited values', () => {
    const original = profile()
    const incoming = structuredClone(original)
    incoming.experience[0]!.title = 'Senior Engineer'
    incoming.experience[0]!.end_date = '2025'
    incoming.experience[0]!.location = 'New office'
    incoming.experience[0]!.bullets = ['New top point', 'New second point']
    const plan = createImportPlan(original, incoming)
    expect(plan.experience).toHaveLength(1)
    expect(plan.experience[0]!.changed).toBe(true)
    expect(applyImportPlan(plan).experience).toEqual(original.experience)
    plan.experience[0]!.fields.find(field => field.key === 'end_date')!.choice = 'incoming'
    for (const point of plan.experience[0]!.lists[0]!.items) {
      point.selected = ['Most important', 'New second point'].includes(point.value)
    }
    expect(applyImportPlan(plan).experience).toEqual([{
      ...original.experience[0]!, end_date: '2025', bullets: ['Most important', 'New second point'],
    }])
    expect(original).toEqual(profile())
  })

  it('matches and compares individual fields and list items in every structured section', () => {
    const original = profile()
    const incoming = structuredClone(original)
    incoming.education[0]!.details = ['New education detail']
    incoming.projects[0]!.bullets = ['New contribution']
    incoming.publications[0]!.authors.reverse()
    incoming.certifications[0]!.date = '2025'
    incoming.languages[0]!.proficiency = 'Native'
    const plan = createImportPlan(original, incoming)
    for (const key of ['education', 'projects', 'publications', 'certifications', 'languages'] as const) {
      expect(plan[key]).toHaveLength(1)
      expect(plan[key][0]!.changed).toBe(true)
      for (const field of plan[key][0]!.fields) field.choice = 'incoming'
      for (const list of plan[key][0]!.lists) {
        for (const point of list.items) point.selected = point.source !== 'current'
      }
    }
    expect(applyImportPlan(plan)).toEqual(incoming)
  })

  it('allows new entries and skills to be skipped without affecting old content', () => {
    const original = profile()
    const incoming = emptyResume()
    incoming.skills = ['SQL', 'Rust', 'Rust']
    incoming.projects = [{ name: 'New project', url: '', bullets: ['New point'] }]
    const plan = createImportPlan(original, incoming)
    expect(applyImportPlan(plan).skills).toEqual(['Python', 'SQL', 'Rust'])
    expect(applyImportPlan(plan).projects).toEqual([...original.projects, ...incoming.projects])
    plan.skills.at(-1)!.choice = 'skip'
    plan.projects.at(-1)!.include = false
    expect(applyImportPlan(plan)).toEqual(original)
  })

  it('does not guess which ambiguous work entry a new version should replace', () => {
    const original = profile()
    original.experience.push({ ...original.experience[0]!, bullets: ['Another existing version'] })
    const incoming = profile()
    incoming.experience[0]!.bullets = ['Uncertain replacement']
    const plan = createImportPlan(original, incoming)
    expect(plan.experience).toHaveLength(3)
    expect(plan.experience[2]!.current).toBeNull()
    expect(applyImportPlan(plan).experience.slice(0, 2)).toEqual(original.experience)
  })

  it('reserves exact matches before pairing a changed duplicate identity', () => {
    const original = profile()
    original.experience.push({ ...original.experience[0]!, bullets: ['Second existing version'] })
    const incoming = profile()
    incoming.experience.unshift({ ...incoming.experience[0]!, bullets: ['Updated second version'] })
    const plan = createImportPlan(original, incoming)
    expect(plan.experience).toHaveLength(2)
    expect(plan.experience[0]!.changed).toBe(false)
    expect(plan.experience[1]!.changed).toBe(true)
    for (const point of plan.experience[1]!.lists[0]!.items) point.selected = point.source === 'incoming'
    expect(applyImportPlan(plan).experience.map(entry => entry.bullets)).toEqual([['Most important', 'Earlier point'], ['Updated second version']])
  })

  it('matches a paper by DOI even when the title changes, without changing author order', () => {
    const original = profile()
    const incoming = profile()
    incoming.publications[0]!.title = 'Different printed title'
    incoming.publications[0]!.doi = 'https://doi.org/10.1234/paper'
    const plan = createImportPlan(original, incoming)
    expect(plan.publications).toHaveLength(1)
    for (const field of plan.publications[0]!.fields) field.choice = 'incoming'
    expect(applyImportPlan(plan).publications[0]).toEqual(incoming.publications[0])
  })

  it('creates the initial draft entirely from selected new content', () => {
    const incoming = profile()
    expect(applyImportPlan(createImportPlan(emptyResume(), incoming))).toEqual(incoming)
  })

  it('does not re-add identical uploaded entries or delete duplicates already present in the source', () => {
    const original = profile()
    const incoming = profile()
    incoming.publications.push(structuredClone(incoming.publications[0]!))
    const plan = createImportPlan(original, incoming)
    expect(plan.publications.filter(item => item.changed)).toEqual([])
    expect(applyImportPlan(plan).publications).toEqual(original.publications)
    expect(applyImportPlan(createImportPlan(emptyResume(), incoming)).publications).toHaveLength(1)
    original.publications.push(structuredClone(original.publications[0]!))
    expect(applyImportPlan(createImportPlan(original, incoming)).publications).toHaveLength(2)
  })

  it('compares corrected start dates within the same role instead of duplicating the entire job', () => {
    const original = profile()
    const incoming = profile()
    incoming.experience[0]!.start_date = '2021'
    const plan = createImportPlan(original, incoming)
    expect(plan.experience).toHaveLength(1)
    expect(plan.experience[0]!.fields.map(field => field.key)).toEqual(['start_date'])
    plan.experience[0]!.fields[0]!.choice = 'incoming'
    expect(applyImportPlan(plan).experience[0]).toEqual({ ...original.experience[0], start_date: '2021' })
  })

  it('hides an omitted scalar or list field rather than clearing existing entry details', () => {
    const original = profile()
    const incoming = profile()
    incoming.experience[0]!.location = ''
    incoming.experience[0]!.bullets = []
    incoming.publications[0]!.authors = []
    incoming.publications[0]!.details = []
    const plan = createImportPlan(original, incoming)
    expect(plan.experience[0]!.changed).toBe(false)
    expect(plan.publications[0]!.changed).toBe(false)
    expect(applyImportPlan(plan)).toEqual(original)
  })

  it('shows a shared point once, skips duplicate new points and preserves old-point priority', () => {
    const original = profile()
    const incoming = profile()
    incoming.experience[0]!.bullets = ['Earlier point', 'Most important', 'New point', 'New point']
    const plan = createImportPlan(original, incoming)
    const items = plan.experience[0]!.lists[0]!.items
    expect(items.map(point => [point.value, point.source, point.selected])).toEqual([
      ['Most important', 'both', true], ['Earlier point', 'both', true], ['New point', 'incoming', false],
    ])
    items[2]!.selected = true
    expect(applyImportPlan(plan).experience[0]!.bullets).toEqual(['Most important', 'Earlier point', 'New point'])
  })

  it('does not flag reordered identical points or silently reorder the source', () => {
    const original = profile()
    const incoming = profile()
    incoming.experience[0]!.bullets.reverse()
    const plan = createImportPlan(original, incoming)
    expect(plan.experience[0]!.changed).toBe(false)
    expect(applyImportPlan(plan)).toEqual(original)
  })

  it('keeps paper authors in source order when only a venue is selected', () => {
    const original = profile()
    const incoming = profile()
    incoming.publications[0]!.authors.reverse()
    incoming.publications[0]!.venue = 'New Conference'
    const plan = createImportPlan(original, incoming)
    expect(plan.publications[0]!.fields.map(field => field.key)).toEqual(['authors', 'venue'])
    expect(plan.publications[0]!.lists).toEqual([])
    plan.publications[0]!.fields.find(field => field.key === 'venue')!.choice = 'incoming'
    expect(applyImportPlan(plan).publications[0]).toEqual({ ...original.publications[0], venue: 'New Conference' })
    plan.publications[0]!.fields.find(field => field.key === 'authors')!.choice = 'incoming'
    expect(applyImportPlan(plan).publications[0]!.authors).toEqual(['Second Author', 'First Author'])
  })

  it('selects newly populated fields without replacing existing neighboring fields', () => {
    const original = profile()
    original.publications[0]!.doi = ''
    const incoming = profile()
    incoming.publications[0]!.venue = 'Different venue'
    const plan = createImportPlan(original, incoming)
    expect(applyImportPlan(plan).publications[0]).toEqual({ ...original.publications[0], doi: incoming.publications[0]!.doi })
  })

  it('returns independent arrays for later editing without modifying the source or candidate', () => {
    const original = profile()
    const incoming = profile()
    incoming.publications[0]!.authors.reverse()
    const plan = createImportPlan(original, incoming)
    plan.publications[0]!.fields[0]!.choice = 'incoming'
    const result = applyImportPlan(plan)
    result.experience[0]!.bullets[0] = 'Later editor change'
    result.publications[0]!.authors.push('Later author change')
    expect(original).toEqual(profile())
    expect(incoming.publications[0]!.authors).toEqual(['Second Author', 'First Author'])
  })

  it('compares a renamed project by its unchanged URL without folding case-sensitive URL paths', () => {
    const original = profile()
    original.projects[0]!.url = 'https://example.test/Project'
    const incoming = profile()
    incoming.projects[0]!.name = 'Renamed project'
    incoming.projects[0]!.url = original.projects[0]!.url
    const plan = createImportPlan(original, incoming)
    expect(plan.projects).toHaveLength(1)
    expect(plan.projects[0]!.fields.map(field => field.key)).toEqual(['name'])
    plan.projects[0]!.fields[0]!.choice = 'incoming'
    expect(applyImportPlan(plan).projects[0]!.name).toBe('Renamed project')
    incoming.projects[0]!.url = 'https://example.test/project'
    expect(createImportPlan(original, incoming).projects).toHaveLength(2)
  })

  it('fills blank source facts without replacing manual wording, order or nonempty sections', () => {
    const current = profile()
    current.contact.phone = ''
    current.summary = ''
    current.education = []
    current.experience[0]!.end_date = ''
    current.experience[0]!.location = 'Hand-edited location'
    current.publications[0]!.authors = []
    const source = profile()
    source.contact.phone = '+1 555 0100'
    source.experience[0]!.bullets = ['Different source point']
    source.experience.push({ ...source.experience[0]!, company: 'Another company', bullets: ['Do not append unknown entry'] })
    source.skills.push('Rust')
    const result = fillResumeGaps(current, source)
    expect(result.contact.phone).toBe('+1 555 0100')
    expect(result.summary).toBe(source.summary)
    expect(result.education).toEqual(source.education)
    expect(result.experience).toEqual([{ ...current.experience[0]!, end_date: '2024' }])
    expect(result.publications[0]!.authors).toEqual(source.publications[0]!.authors)
    expect(result.skills).toEqual(current.skills)
    expect(current.contact.phone).toBe('')
    expect(current.education).toEqual([])
    result.education[0]!.details.push('Local-only edit')
    expect(source.education[0]!.details).toEqual(['Original detail'])
  })

  it('can fill empty list fields of uniquely matched entries and ignores uncertain correspondence', () => {
    const current = profile()
    current.experience[0]!.bullets = []
    current.projects[0]!.bullets = []
    current.skills = []
    const source = profile()
    expect(fillResumeGaps(current, source).experience[0]!.bullets).toEqual(source.experience[0]!.bullets)
    expect(fillResumeGaps(current, source).projects[0]!.bullets).toEqual(source.projects[0]!.bullets)
    expect(fillResumeGaps(current, source).skills).toEqual(source.skills)
    source.experience.push({ ...source.experience[0]!, end_date: '2026', bullets: ['Ambiguous version'] })
    expect(fillResumeGaps(current, source).experience[0]!.bullets).toEqual([])
  })
})
