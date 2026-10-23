<script setup lang="ts">
import type { ResumeProfile } from '../types'
import ResumeSection from './ResumeSection.vue'
defineProps<{ profile: ResumeProfile }>()
</script>
<template>
  <div class="resume-preview">
    <h1>{{ profile.contact.name }}</h1>
    <p class="hint">{{ [profile.contact.email, profile.contact.phone, profile.contact.location, profile.contact.linkedin, profile.contact.website].filter(Boolean).join(' | ') }}</p>
    <template v-if="profile.summary"><h2>个人简介</h2><p>{{ profile.summary }}</p></template>
    <template v-if="profile.skills.length"><h2>技能</h2><p>{{ profile.skills.join(' · ') }}</p></template>
    <template v-if="profile.experience.length">
      <h2>工作经历</h2>
      <section v-for="(entry, index) in profile.experience" :key="index">
        <h3>{{ [entry.title, entry.company, entry.location, entry.start_date, entry.end_date].filter(Boolean).join(' | ') }}</h3>
        <ul><li v-for="(point, position) in entry.bullets" :key="position">{{ point }}</li></ul>
      </section>
    </template>
    <ResumeSection v-if="profile.education.length" title="教育经历" :count="profile.education.length" data-preview-section="education"><section v-for="(entry, index) in profile.education" :key="index"><h3>{{ [entry.institution, entry.degree, entry.field, entry.start_date, entry.end_date].filter(Boolean).join(' | ') }}</h3><ul><li v-for="(item, position) in entry.details" :key="position">{{ item }}</li></ul></section></ResumeSection>
    <ResumeSection v-if="profile.publications.length" title="论文 / Publications" :count="profile.publications.length" data-preview-section="publications">
      <section v-for="(entry, index) in profile.publications" :key="index">
        <h3 v-if="entry.title">{{ entry.title }}</h3>
        <p>{{ [entry.authors.join(', '), entry.venue, entry.date, entry.doi ? `DOI: ${entry.doi}` : '', entry.url].filter(Boolean).join(' | ') }}</p>
        <ul v-if="entry.details.length"><li v-for="(item, position) in entry.details" :key="position">{{ item }}</li></ul>
      </section>
    </ResumeSection>
    <ResumeSection v-if="profile.projects.length" title="项目经历" :count="profile.projects.length" data-preview-section="projects"><section v-for="(entry, index) in profile.projects" :key="index"><h3>{{ entry.name }} {{ entry.url }}</h3><ul><li v-for="(item, position) in entry.bullets" :key="position">{{ item }}</li></ul></section></ResumeSection>
    <ResumeSection v-if="profile.certifications.length" title="证书" :count="profile.certifications.length" data-preview-section="certifications"><p v-for="(entry, index) in profile.certifications" :key="index">{{ [entry.name, entry.issuer, entry.date].filter(Boolean).join(' | ') }}</p></ResumeSection>
    <ResumeSection v-if="profile.languages.length" title="语言" :count="profile.languages.length" data-preview-section="languages"><p v-for="(entry, index) in profile.languages" :key="index">{{ entry.name }} {{ entry.proficiency }}</p></ResumeSection>
  </div>
</template>
