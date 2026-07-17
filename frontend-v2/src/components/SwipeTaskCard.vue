<template>
  <div class="swipe-task-card" ref="cardRef">
    <!-- 背景操作按钮（左滑时露出） -->
    <div class="swipe-actions">
      <button class="action-btn action-edit" @click.stop="$emit('edit')">✏️ 编辑</button>
      <button class="action-btn action-done" @click.stop="$emit('done')">✅ 完成</button>
      <button class="action-btn action-delete" @click.stop="$emit('delete')">🗑️ 删除</button>
    </div>
    <!-- 前景内容 -->
    <div class="card-content" :style="contentStyle" @touchstart.passive="handleTouchStart" @touchmove.passive="handleTouchMove" @touchend="handleTouchEnd">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const emit = defineEmits<{
  edit: []
  done: []
  delete: []
}>()

const translateX = ref(0)
const maxSwipe = 180 // 最大滑动距离（3个按钮宽度）

let startX = 0
let currentX = 0
let isSwiping = false

const contentStyle = computed(() => ({
  transform: `translateX(${translateX.value}px)`,
  transition: isSwiping ? 'none' : 'transform 0.3s ease'
}))

function handleTouchStart(e: TouchEvent) {
  startX = e.touches[0].clientX
  currentX = startX
  isSwiping = true
}

function handleTouchMove(e: TouchEvent) {
  if (!isSwiping) return
  currentX = e.touches[0].clientX
  const dx = currentX - startX
  // 仅响应左滑（手指右移，内容左移）
  if (dx > 0) {
    translateX.value = Math.min(dx, maxSwipe)
  }
}

function handleTouchEnd() {
  isSwiping = false
  const dx = currentX - startX
  if (dx > 80) {
    translateX.value = maxSwipe
  } else {
    translateX.value = 0
  }
}

// 点击前景关闭滑动
function closeSwipe() {
  translateX.value = 0
}

defineExpose({ closeSwipe })
</script>

<style scoped>
.swipe-task-card {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.swipe-actions {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: row-reverse;
  z-index: 0;
}

.action-btn {
  width: 60px;
  border: none;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  letter-spacing: 1px;
}

.action-edit { background: #409EFF; }
.action-done { background: #67C23A; }
.action-delete { background: #F56C6C; }

.card-content {
  position: relative;
  z-index: 1;
  will-change: transform;
}
</style>
