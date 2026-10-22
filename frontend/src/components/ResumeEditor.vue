<script setup lang="ts">
import EntryList from './EntryList.vue'
import type { Contact, FieldDefinition, ResumeProfile } from '../types'
import { lines } from '../lib/forms'

const model = defineModel<ResumeProfile>({ required: true })
const emit = defineEmits<{ change: [] }>()
const contacts: { key: keyof Contact; label: string }[] = [
  { key: 'name', label: '姓名' }, { key: 'email', label: '邮箱' }, { key: 'phone', label: '电话' },
  { key: 'location', label: '所在地' }, { key: 'linkedin', label: 'LinkedIn' }, { key: 'website', label: '网站 / 作品集' },
]
const experience: FieldDefinition[] = [
  { key: 'company', label: '公司' }, { key: 'title', label: '职位' }, { key: 'location', label: '地点' },
  { key: 'start_date', label: '开始日期' }, { key: 'end_date', label: '结束日期' }, { key: 'bullets', label: '工作要点', multiline: true },
]
const education: FieldDefinition[] = [
  { key: 'institution', label: '院校' }, { key: 'degree', label: '学位' }, { key: 'field', label: '专业' },
  { key: 'start_date', label: '开始日期' }, { key: 'end_date', label: '结束日期' }, { key: 'details', label: '补充信息（每行一项）', multiline: true },
]
const projects: FieldDefinition[] = [{ key: 'name', label: '项目名称' }, { key: 'url', label: '链接' }, { key: 'bullets', label: '项目要点（每行一项）', multiline: true }]
const certifications: FieldDefinition[] = [{ key: 'name', label: '证书名称' }, { key: 'issuer', label: '颁发机构' }, { key: 'date', label: '日期' }]
const languages: FieldDefinition[] = [{ key: 'name', label: '语言' }, { key: 'proficiency', label: '熟练程度' }]
function skills(event: Event) {
  if (!(event.target instanceof HTMLTextAreaElement)) throw new Error('技能编辑控件异常')
  model.value.skills = lines(event.target.value)
  emit('change')
}
</script>
<template>
  <div class="resume-editor">
    <div class="form-grid">
      <label v-for="field in contacts" :key="field.key">{{ field.label }}<input v-model="model.contact[field.key]" maxlength="500" @input="emit('change')"></label>
    </div>
    <label>个人简介<textarea v-model="model.summary" rows="4" maxlength="10000" @input="emit('change')" /></label>
    <label>技能（每行一项）<textarea :value="model.skills.join('\n')" rows="4" @input="skills" /></label>
    <EntryList title="工作经历" section="experience" :entries="model.experience" :fields="experience" :create="() => ({ company: '', title: '', location: '', start_date: '', end_date: '', bullets: [] })" work-points @change="emit('change')" />
    <EntryList title="教育经历" section="education" :entries="model.education" :fields="education" :create="() => ({ institution: '', degree: '', field: '', start_date: '', end_date: '', details: [] })" @change="emit('change')" />
    <EntryList title="项目经历" section="projects" :entries="model.projects" :fields="projects" :create="() => ({ name: '', url: '', bullets: [] })" @change="emit('change')" />
    <EntryList title="证书" section="certifications" :entries="model.certifications" :fields="certifications" :create="() => ({ name: '', issuer: '', date: '' })" @change="emit('change')" />
    <EntryList title="语言" section="languages" :entries="model.languages" :fields="languages" :create="() => ({ name: '', proficiency: '' })" @change="emit('change')" />
  </div>
</template>
