<script setup lang="ts">
import WorkPointList from './WorkPointList.vue'
import { lines } from '../lib/forms'
import type { EditableEntry, FieldDefinition } from '../types'

const props = defineProps<{
  title: string; section: string; entries: EditableEntry[]
  fields: FieldDefinition[]; create: () => EditableEntry; workPoints?: boolean
}>()
const emit = defineEmits<{ change: [] }>()
function value(entry: EditableEntry, field: FieldDefinition): string {
  const data = entry[field.key]
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.join('\n')
  throw new Error(`简历字段 ${field.key} 数据缺失`)
}
function update(entry: EditableEntry, field: FieldDefinition, event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement)) throw new Error('简历编辑控件类型错误')
  entry[field.key] = field.multiline ? lines(input.value) : input.value
  emit('change')
}
function bullets(entry: EditableEntry): string[] {
  const data = entry.bullets
  if (!Array.isArray(data)) throw new Error('工作要点必须是列表')
  return data
}
function setBullets(entry: EditableEntry, value: string[]) { entry.bullets = value }
function add() { props.entries.push(props.create()); emit('change') }
function remove(index: number) { props.entries.splice(index, 1); emit('change') }
</script>
<template>
  <section class="editor-section" :data-section="section">
    <div class="section-heading"><h3>{{ title }}</h3><button type="button" class="secondary small" @click="add">添加一项</button></div>
    <div v-for="(entry, index) in entries" :key="index" class="entry">
      <div class="form-grid">
        <template v-for="field in fields" :key="field.key">
          <label v-if="!(workPoints && field.key === 'bullets')">{{ field.label }}
            <textarea v-if="field.multiline" :value="value(entry, field)" rows="4" maxlength="80000" @input="update(entry, field, $event)" />
            <input v-else :value="value(entry, field)" maxlength="500" @input="update(entry, field, $event)">
          </label>
        </template>
      </div>
      <WorkPointList v-if="workPoints" :model-value="bullets(entry)" @update:model-value="setBullets(entry, $event)" @change="emit('change')" />
      <button type="button" class="secondary danger small" @click="remove(index)">删除此项</button>
    </div>
  </section>
</template>
