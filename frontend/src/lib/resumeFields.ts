import type { Contact, FieldDefinition } from '../types'

export const contactFields: { key: keyof Contact; label: string }[] = [
  { key: 'name', label: '姓名' }, { key: 'email', label: '邮箱' }, { key: 'phone', label: '电话' },
  { key: 'location', label: '所在地' }, { key: 'linkedin', label: 'LinkedIn' }, { key: 'website', label: '网站 / 作品集' },
]

export const entryFields = {
  experience: [
    { key: 'company', label: '公司' }, { key: 'title', label: '职位' }, { key: 'location', label: '地点' },
    { key: 'start_date', label: '开始日期' }, { key: 'end_date', label: '结束日期' }, { key: 'bullets', label: '工作要点', multiline: true },
  ],
  education: [
    { key: 'institution', label: '院校' }, { key: 'degree', label: '学位' }, { key: 'field', label: '专业' },
    { key: 'start_date', label: '开始日期' }, { key: 'end_date', label: '结束日期' }, { key: 'details', label: '补充信息（每行一项）', multiline: true },
  ],
  publications: [
    { key: 'title', label: '论文标题' }, { key: 'authors', label: '作者（每行一位，保持署名顺序）', multiline: true },
    { key: 'venue', label: '期刊 / 会议 / 发表平台' }, { key: 'date', label: '发表时间 / 年份' },
    { key: 'doi', label: 'DOI' }, { key: 'url', label: '论文链接' },
    { key: 'details', label: '其他引文信息（卷期、页码、预印本编号等，每行一项）', multiline: true },
  ],
  projects: [{ key: 'name', label: '项目名称' }, { key: 'url', label: '链接' }, { key: 'bullets', label: '项目要点（每行一项）', multiline: true }],
  certifications: [{ key: 'name', label: '证书名称' }, { key: 'issuer', label: '颁发机构' }, { key: 'date', label: '日期' }],
  languages: [{ key: 'name', label: '语言' }, { key: 'proficiency', label: '熟练程度' }],
} satisfies Record<string, FieldDefinition[]>

export type EntrySection = keyof typeof entryFields
export const sectionLabels: Record<EntrySection, string> = {
  experience: '工作经历', education: '教育经历', publications: '论文 / Publications',
  projects: '项目经历', certifications: '证书', languages: '语言',
}
