<script setup lang="ts">
import EntryList from './EntryList.vue'
import type { ResumeProfile } from '../types'
import { lines } from '../lib/forms'
import { contactFields, entryFields } from '../lib/resumeFields'

const model = defineModel<ResumeProfile>({ required: true })
const emit = defineEmits<{ change: [] }>()
function skills(event: Event) {
  if (!(event.target instanceof HTMLTextAreaElement)) throw new Error('技能编辑控件异常')
  model.value.skills = lines(event.target.value)
  emit('change')
}
</script>
<template>
  <div class="resume-editor">
    <div class="form-grid">
      <label v-for="field in contactFields" :key="field.key">{{ field.label }}<input v-model="model.contact[field.key]" maxlength="500" @input="emit('change')"></label>
    </div>
    <label>个人简介<textarea v-model="model.summary" rows="4" maxlength="10000" @input="emit('change')" /></label>
    <label>技能（每行一项）<textarea :value="model.skills.join('\n')" rows="4" @input="skills" /></label>
    <EntryList title="工作经历" section="experience" :entries="model.experience" :fields="entryFields.experience" :create="() => ({ company: '', title: '', location: '', start_date: '', end_date: '', bullets: [] })" work-points @change="emit('change')" />
    <EntryList title="教育经历" section="education" :entries="model.education" :fields="entryFields.education" :create="() => ({ institution: '', degree: '', field: '', start_date: '', end_date: '', details: [] })" @change="emit('change')" />
    <EntryList title="论文 / Publications" section="publications" :entries="model.publications" :fields="entryFields.publications" :create="() => ({ title: '', authors: [], venue: '', date: '', doi: '', url: '', details: [] })" @change="emit('change')" />
    <EntryList title="项目经历" section="projects" :entries="model.projects" :fields="entryFields.projects" :create="() => ({ name: '', url: '', bullets: [] })" @change="emit('change')" />
    <EntryList title="证书" section="certifications" :entries="model.certifications" :fields="entryFields.certifications" :create="() => ({ name: '', issuer: '', date: '' })" @change="emit('change')" />
    <EntryList title="语言" section="languages" :entries="model.languages" :fields="entryFields.languages" :create="() => ({ name: '', proficiency: '' })" @change="emit('change')" />
  </div>
</template>
