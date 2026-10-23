<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EditableEntry, ResumeProfile } from '../types'
import { applyImportPlan, createImportPlan } from '../lib/resumeImport'
import { entryFields, sectionLabels, type EntrySection } from '../lib/resumeFields'
import ResumeSection from './ResumeSection.vue'

const props = defineProps<{ current: ResumeProfile; incoming: ResumeProfile; filename: string; disabled: boolean }>()
const emit = defineEmits<{ apply: [profile: ResumeProfile]; discard: []; change: [] }>()
const plan = ref(createImportPlan(props.current, props.incoming))
const sections = computed(() => (Object.keys(sectionLabels) as EntrySection[]).map(key => ({
  key, title: sectionLabels[key], items: plan.value[key].filter(item => item.changed),
})).filter(section => section.items.length))
const newSkills = computed(() => plan.value.skills.filter(item => item.changed))
const count = computed(() => plan.value.scalars.length + newSkills.value.length + sections.value.reduce((total, section) => total + section.items.length, 0))
function display(entry: EditableEntry | null, key: string) {
  const value = entry?.[key]
  return Array.isArray(value) ? value.join('\n') : value || ''
}
function fieldText(value: string | string[]) { return Array.isArray(value) ? value.join('\n') : value || '（空）' }
function heading(section: EntrySection, entry: EditableEntry | null) {
  return entryFields[section].map(field => entry?.[field.key]).filter((value): value is string => typeof value === 'string' && !!value).slice(0, 2).join(' · ')
}
function apply() { emit('apply', applyImportPlan(plan.value)) }
</script>
<template>
  <section class="card import-review" aria-labelledby="import-title">
    <h2 id="import-title">新上传内容对比 · {{ filename }}</h2>
    <p class="hint">解析结果已单独保存，当前草稿和已确认底板没有被覆盖。相同内容不重复提示；原有内容不会因新文件缺失而删除。</p>
    <p class="notice">不同字段分别选择，默认保留已有值。工作要点及补充信息可逐条勾选；已有条目中的新要点默认不选，避免冲掉手工修改。全新条目默认选中，应用后仍可编辑或删除。</p>
    <form @submit.prevent="apply"><fieldset :disabled="disabled" class="stack">
      <p v-if="!count" class="notice">没有需要处理的新增或差异内容，应用后仍保留当前内容，也可以直接放弃本次上传。</p>
      <article v-for="item in plan.scalars" :key="item.key" class="import-item" :data-import-field="item.key">
        <h3>{{ item.label }} <span class="badge">{{ item.current ? '内容不同' : '新增内容' }}</span></h3>
        <div class="import-columns">
          <label class="import-option" :class="{ selected: item.choice === 'current' }"><span class="check"><input v-model="item.choice" type="radio" :name="`import-${item.key}`" value="current" @change="emit('change')">保留现有</span><span class="prose">{{ item.current || '（空）' }}</span></label>
          <label class="import-option" :class="{ selected: item.choice === 'incoming' }"><span class="check"><input v-model="item.choice" type="radio" :name="`import-${item.key}`" value="incoming" @change="emit('change')">采用新内容</span><span class="prose">{{ item.incoming }}</span></label>
        </div>
        <label v-if="item.key === 'summary' && item.current" class="check"><input v-model="item.choice" type="radio" name="import-summary" value="both" @change="emit('change')">两段都保留，之后自行修改</label>
      </article>
      <section v-if="newSkills.length" data-import-section="skills"><h3>新增技能</h3><label v-for="(item, index) in newSkills" :key="index" class="check"><input v-model="item.choice" type="checkbox" true-value="incoming" false-value="skip" @change="emit('change')">{{ item.incoming }}</label></section>
      <ResumeSection v-for="section in sections" :key="section.key" :data-import-section="section.key" :title="section.title" :count="section.items.length" :initially-open="section.key === 'experience'">
        <article v-for="(item, index) in section.items" :key="index" class="import-item">
          <h4>{{ heading(section.key, item.current || item.incoming) }}</h4>
          <template v-if="item.current">
            <p class="hint">仅展示不同字段及要点；相同字段、未提供的旧字段和现有条目顺序保持不变。</p>
            <section v-for="field in item.fields" :key="field.key" class="import-field" :data-import-field="field.key">
              <h4>{{ field.label }}</h4>
              <p v-if="field.key === 'authors'" class="hint">作者名单按原署名顺序整体选择，不拼接或重排作者。</p>
              <div class="import-columns">
                <label v-for="side in (['current', 'incoming'] as const)" :key="side" class="import-option" :class="{ selected: field.choice === side }">
                  <span class="check"><input v-model="field.choice" type="radio" :name="`import-${section.key}-${index}-${field.key}`" :value="side" @change="emit('change')">{{ side === 'current' ? '保留现有值' : '采用新值' }}</span>
                  <span class="prose">{{ fieldText(field[side]) }}</span>
                </label>
              </div>
            </section>
            <section v-for="list in item.lists" :key="list.key" class="import-field" :data-import-list="list.key">
              <h4>{{ list.label }}</h4>
              <p class="hint">逐条勾选要保留的内容，可取消旧要点并选用新要点。不按行号猜测对应关系；相同要点只展示一次，新选要点追加到末尾，应用后可调整顺序。</p>
              <div class="import-columns">
                <div v-for="side in (['current', 'incoming'] as const)" :key="side" class="import-option">
                  <h5>{{ side === 'current' ? '现有内容（保持原顺序）' : '新解析内容（按需选入）' }}</h5>
                  <label v-for="(point, pointIndex) in list.items.filter(point => side === 'current' ? point.source !== 'incoming' : point.source === 'incoming')" :key="pointIndex" class="import-point" :data-point-source="point.source" :class="{ selected: point.selected }">
                    <span class="check"><input v-model="point.selected" type="checkbox" @change="emit('change')"><span class="prose">{{ point.value }}</span></span>
                    <span class="badge">{{ point.source === 'both' ? '两份都有' : point.source === 'current' ? '仅现有内容' : '新解析内容' }}</span>
                  </label>
                </div>
              </div>
            </section>
          </template>
          <div v-else class="import-option" :class="{ selected: item.include }" data-new-entry>
            <label class="check"><input v-model="item.include" type="checkbox" @change="emit('change')">添加这条新内容 / 未确定对应关系</label>
            <dl><template v-for="field in entryFields[section.key]" :key="field.key"><template v-if="display(item.incoming, field.key)"><dt>{{ field.label }}</dt><dd>{{ display(item.incoming, field.key) }}</dd></template></template></dl>
          </div>
        </article>
      </ResumeSection>
      <div class="button-row"><button type="submit">应用所选内容到草稿</button><button type="button" class="secondary" @click="emit('discard')">放弃本次上传，保留原内容</button></div>
      <p class="hint">应用只保存草稿，不会改变已确认底板；之后仍需核对并确认保存。</p>
    </fieldset></form>
  </section>
</template>
