<script setup lang="ts">
import { nextTick, onMounted, onUpdated, ref } from 'vue'
import { moveItem } from '../lib/forms'

const points = defineModel<string[]>({ required: true })
const emit = defineEmits<{ change: [] }>()
const list = ref<HTMLElement | null>(null)
function updateValidity() {
  list.value?.querySelectorAll('textarea').forEach(input => {
    input.setCustomValidity(input.value.trim() ? '' : '请输入工作要点，或删除这一条')
  })
}
onMounted(updateValidity)
onUpdated(updateValidity)
async function move(index: number, offset: number) {
  points.value = moveItem(points.value, index, index + offset)
  emit('change')
  await nextTick()
  list.value?.querySelectorAll<HTMLTextAreaElement>('textarea')[index + offset]?.focus()
}
async function add() {
  if (points.value.length >= 50) throw new RangeError('每段经历最多 50 条工作要点')
  points.value = [...points.value, '']
  emit('change')
  await nextTick()
  const inputs = list.value?.querySelectorAll<HTMLTextAreaElement>('textarea')
  inputs?.item(inputs.length - 1)?.focus()
}
function remove(index: number) {
  points.value = points.value.filter((_, position) => position !== index)
  emit('change')
}
function validate(event: Event) {
  const input = event.target
  if (input instanceof HTMLTextAreaElement) input.setCustomValidity(input.value.trim() ? '' : '请输入工作要点，或删除这一条')
  emit('change')
}
</script>
<template>
  <section class="work-bullets">
    <div class="section-heading"><h4>工作要点</h4><button type="button" class="secondary small" :disabled="points.length >= 50" @click="add">添加工作要点</button></div>
    <p class="hint">越靠上越重要、越新；排序随本份简历保存。每条可换行，最多 50 条。</p>
    <div ref="list" class="work-bullet-list">
      <p v-if="!points.length" class="hint">暂无工作要点，可逐条添加。</p>
      <div v-for="(_, index) in points" :key="index" class="work-bullet-entry">
        <label>工作要点 {{ index + 1 }}<textarea v-model="points[index]" rows="3" maxlength="10000" required placeholder="填写这一条工作要点，可在条目内换行" @input="validate" /></label>
        <div class="button-row work-bullet-actions">
          <button type="button" class="secondary small" data-move="up" :aria-label="`上移工作要点 ${index + 1}`" :disabled="index === 0" @click="move(index, -1)">上移</button>
          <button type="button" class="secondary small" data-move="down" :aria-label="`下移工作要点 ${index + 1}`" :disabled="index === points.length - 1" @click="move(index, 1)">下移</button>
          <button type="button" class="secondary danger small" :aria-label="`删除工作要点 ${index + 1}`" @click="remove(index)">删除工作要点</button>
        </div>
      </div>
    </div>
  </section>
</template>
