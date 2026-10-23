import type { Contact, EditableEntry, FieldDefinition, ResumeProfile } from '../types'
import { contactFields, entryFields, type EntrySection } from './resumeFields'

export type ImportChoice = 'current' | 'incoming' | 'both' | 'skip'
export type ImportItem<T> = { current: T | null; incoming: T | null; choice: ImportChoice; changed: boolean }
export type ScalarChange = ImportItem<string> & { key: keyof Contact | 'summary'; label: string }
type FieldValue = string | string[]
export type EntryFieldChange = { key: string; label: string; current: FieldValue; incoming: FieldValue; choice: 'current' | 'incoming' }
export type PointChoice = { value: string; source: 'current' | 'incoming' | 'both'; selected: boolean }
export type PointChange = { key: string; label: string; items: PointChoice[] }
export type EntryImport<T> = {
  current: T | null; incoming: T | null; include: boolean; changed: boolean
  fields: EntryFieldChange[]; lists: PointChange[]
}
type EntryPlan = { [K in EntrySection]: EntryImport<ResumeProfile[K][number]>[] }
export type ImportPlan = EntryPlan & {
  original: ResumeProfile; scalars: ScalarChange[]; skills: ImportItem<string>[]
}

const normalize = (value: string) => value.trim().replace(/\s+/g, ' ')
function sameValue(left: FieldValue, right: FieldValue): boolean {
  if (Array.isArray(left) && Array.isArray(right)) return JSON.stringify(left.map(normalize)) === JSON.stringify(right.map(normalize))
  return typeof left === 'string' && typeof right === 'string' && normalize(left) === normalize(right)
}
function sameEntry(left: EditableEntry, right: EditableEntry): boolean {
  const normalizeEntry = (entry: EditableEntry) => Object.keys(entry).sort().map(key => {
    const value = entry[key]
    return [key, Array.isArray(value) ? value.map(normalize) : normalize(value ?? '')]
  })
  return JSON.stringify(normalizeEntry(left)) === JSON.stringify(normalizeEntry(right))
}
function identity(section: EntrySection, entry: EditableEntry): string[] {
  const key = (...fields: string[]) => fields.map(field => {
    const value = entry[field]
    return typeof value === 'string' ? normalize(value).toLowerCase() : ''
  })
  const joined = (prefix: string, fields: string[]) => fields.every(Boolean) ? [`${prefix}:${JSON.stringify(fields)}`] : []
  switch (section) {
    case 'experience': return [...joined('role', key('company', 'title')), ...joined('start', key('company', 'start_date'))]
    case 'education': return [...joined('degree', key('institution', 'degree')), ...joined('start', key('institution', 'start_date'))]
    case 'projects': return [
      ...joined('name', key('name')),
      ...joined('url', [typeof entry.url === 'string' ? normalize(entry.url) : '']),
    ]
    case 'certifications': return joined('name', key('name'))
    case 'languages': return joined('name', key('name'))
    case 'publications': {
      const [doi = '', title = ''] = key('doi', 'title')
      return [doi ? `doi:${doi.replace(/^https?:\/\/(?:dx\.)?doi\.org\//, '').replace(/^doi:\s*/, '')}` : '', title ? `title:${title}` : ''].filter(Boolean)
    }
  }
}
function pointChoices(current: string[], incoming: string[]): PointChoice[] {
  const incomingValues = new Set(incoming.map(normalize))
  const seen = new Set(current.map(normalize))
  const result: PointChoice[] = current.map(value => ({
    value, source: incomingValues.has(normalize(value)) ? 'both' : 'current', selected: true,
  }))
  for (const value of incoming) {
    const normalized = normalize(value)
    if (normalized && !seen.has(normalized)) {
      result.push({ value, source: 'incoming', selected: false })
      seen.add(normalized)
    }
  }
  return result
}
function entryChanges(section: EntrySection, current: EditableEntry, incoming: EditableEntry) {
  const fields: EntryFieldChange[] = [], lists: PointChange[] = []
  const definitions: FieldDefinition[] = entryFields[section]
  for (const field of definitions) {
    const oldValue = current[field.key], newValue = incoming[field.key]
    if (oldValue === undefined || newValue === undefined) throw new Error(`简历字段 ${field.key} 数据缺失`)
    if (sameValue(oldValue, newValue) || (typeof newValue === 'string' ? !normalize(newValue) : !newValue.length)) continue
    if (Array.isArray(oldValue) && Array.isArray(newValue) && field.key !== 'authors') {
      const items = pointChoices(oldValue, newValue)
      if (items.some(item => item.source !== 'both')) lists.push({ key: field.key, label: field.label, items })
    } else {
      fields.push({ key: field.key, label: field.label, current: oldValue, incoming: newValue, choice: oldValue.length ? 'current' : 'incoming' })
    }
  }
  return { fields, lists }
}
function entryPlan<T extends EditableEntry>(section: EntrySection, current: T[], incoming: T[]): EntryImport<T>[] {
  incoming = incoming.filter((entry, index, entries) => entries.findIndex(other => sameEntry(other, entry)) === index)
  const pairs = new Map<number, number>()
  const used = new Set<number>()
  // Reserve exact matches before considering identities, so duplicates do not steal them.
  incoming.forEach((entry, newIndex) => {
    const oldIndex = current.findIndex((old, index) => !used.has(index) && sameEntry(old, entry))
    if (oldIndex !== -1) { pairs.set(newIndex, oldIndex); used.add(oldIndex) }
  })
  const related = (old: T, entry: T) => identity(section, old).some(key => identity(section, entry).includes(key))
  incoming.forEach((entry, newIndex) => {
    if (pairs.has(newIndex)) return
    const matches = current.flatMap((old, index) => !used.has(index) && related(old, entry) ? [index] : [])
    const oldIndex = matches[0]
    if (matches.length !== 1 || oldIndex === undefined) return
    const alternatives = incoming.filter((other, index) => !pairs.has(index) && related(current[oldIndex]!, other))
    if (alternatives.length === 1) { pairs.set(newIndex, oldIndex); used.add(oldIndex) }
  })
  const result: EntryImport<T>[] = current.map((entry, oldIndex) => {
    const match = [...pairs].find(([, index]) => index === oldIndex)
    const added = match ? incoming[match[0]]! : null
    const changes = added ? entryChanges(section, entry, added) : { fields: [], lists: [] }
    return { current: entry, incoming: added, include: true, changed: !!(changes.fields.length || changes.lists.length), ...changes }
  })
  incoming.forEach((entry, index) => {
    if (!pairs.has(index)) result.push({ current: null, incoming: entry, include: true, changed: true, fields: [], lists: [] })
  })
  return result
}
export function createImportPlan(original: ResumeProfile, incoming: ResumeProfile): ImportPlan {
  const scalars: ScalarChange[] = []
  for (const { key, label } of [...contactFields, { key: 'summary' as const, label: '个人简介' }]) {
    const oldValue = key === 'summary' ? original.summary : original.contact[key]
    const newValue = key === 'summary' ? incoming.summary : incoming.contact[key]
    if (!normalize(newValue) || normalize(oldValue) === normalize(newValue)) continue
    scalars.push({ key, label, current: oldValue, incoming: newValue, choice: oldValue ? 'current' : 'incoming', changed: true })
  }
  const skills: ImportItem<string>[] = original.skills.map(value => ({ current: value, incoming: null, choice: 'current', changed: false }))
  const seen = new Set(original.skills.map(normalize))
  for (const value of incoming.skills) {
    if (!seen.has(normalize(value))) {
      skills.push({ current: null, incoming: value, choice: 'incoming', changed: true })
      seen.add(normalize(value))
    }
  }
  return {
    original, scalars, skills,
    experience: entryPlan('experience', original.experience, incoming.experience),
    education: entryPlan('education', original.education, incoming.education),
    publications: entryPlan('publications', original.publications, incoming.publications),
    projects: entryPlan('projects', original.projects, incoming.projects),
    certifications: entryPlan('certifications', original.certifications, incoming.certifications),
    languages: entryPlan('languages', original.languages, incoming.languages),
  }
}
function selected<T>(items: ImportItem<T>[]): T[] {
  return items.flatMap(item => {
    switch (item.choice) {
      case 'current': return item.current === null ? [] : [item.current]
      case 'incoming': return item.incoming === null ? [] : [item.incoming]
      case 'both': return [item.current, item.incoming].filter((value): value is T => value !== null)
      case 'skip': return []
    }
  })
}
function copyEntry<T extends EditableEntry>(entry: T): T {
  const copy = { ...entry }
  for (const [key, value] of Object.entries(entry)) {
    if (Array.isArray(value)) Object.assign(copy, { [key]: [...value] })
  }
  return copy
}
function selectedEntries<T extends EditableEntry>(items: EntryImport<T>[]): T[] {
  return items.flatMap(item => {
    if (!item.include) return []
    const source = item.current ?? item.incoming
    if (!source) throw new Error('待合并条目缺少简历内容')
    const entry = copyEntry(source)
    for (const field of item.fields) {
      const value = field[field.choice]
      Object.assign(entry, { [field.key]: Array.isArray(value) ? [...value] : value })
    }
    for (const list of item.lists) {
      Object.assign(entry, { [list.key]: list.items.filter(point => point.selected).map(point => point.value) })
    }
    return [entry]
  })
}
export function applyImportPlan(plan: ImportPlan): ResumeProfile {
  const result: ResumeProfile = {
    ...plan.original, contact: { ...plan.original.contact }, skills: selected(plan.skills),
    experience: selectedEntries(plan.experience), education: selectedEntries(plan.education),
    publications: selectedEntries(plan.publications), projects: selectedEntries(plan.projects),
    certifications: selectedEntries(plan.certifications), languages: selectedEntries(plan.languages),
  }
  for (const item of plan.scalars) {
    const value = item.choice === 'incoming' ? item.incoming! : item.current!
    if (item.key === 'summary') result.summary = item.choice === 'both' ? [item.current, item.incoming].filter(Boolean).join('\n\n') : value
    else result.contact[item.key] = value
  }
  return result
}
