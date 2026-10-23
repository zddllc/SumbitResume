<script setup lang="ts">
import { ref } from 'vue'

withDefaults(defineProps<{ title: string; count: number; initiallyOpen?: boolean }>(), { initiallyOpen: false })
const panel = ref<HTMLDetailsElement | null>(null)
function expand() { if (panel.value) panel.value.open = true }
defineExpose({ expand })
</script>
<template>
  <details ref="panel" class="resume-section" :open="initiallyOpen" @invalid.capture="expand">
    <summary class="resume-section-heading">
      <h3>{{ title }}</h3>
      <span class="badge">{{ count }} 项</span>
      <span class="fold-state fold-closed">展开</span><span class="fold-state fold-open">收起</span>
    </summary>
    <div class="resume-section-content"><slot /></div>
  </details>
</template>
