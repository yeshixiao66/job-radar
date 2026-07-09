<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import JobsPage from './pages/JobsPage.vue'
import MonitorPage from './pages/MonitorPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import { getStatus } from './api'

type Page = 'jobs' | 'monitor' | 'settings'

const activePage = ref<Page>('jobs')
const running = ref(false)
const stopping = ref(false)
let timer: number | undefined

const navItems: { key: Page; label: string; icon: string; desc: string }[] = [
  { key: 'jobs', label: '汇总信息表', icon: '📋', desc: '岗位数据汇总' },
  { key: 'monitor', label: 'Agent 信息', icon: '📡', desc: '抓取进程监控' },
  { key: 'settings', label: 'API 管理', icon: '⚙️', desc: '模型接口配置' },
]

async function refreshStatus() {
  try {
    const s = await getStatus()
    running.value = s.running
    stopping.value = s.stopping
  } catch (e) {
    // 后端未启动时静默
  }
}

onMounted(() => {
  refreshStatus()
  timer = window.setInterval(refreshStatus, 3000)
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="app-shell">
    <aside class="side-nav">
      <div class="brand">
        <div class="brand-mark">JR</div>
        <div>
          <h1>Job Radar</h1>
          <p>求职情报工具</p>
        </div>
      </div>

      <div class="nav-group">
        <div class="nav-group-title">功能导航</div>
        <nav>
          <button
            v-for="item in navItems"
            :key="item.key"
            :class="{ active: activePage === item.key }"
            @click="activePage = item.key"
          >
            <span class="icon">{{ item.icon }}</span>
            <span class="label-block">
              <span class="label-text">{{ item.label }}</span>
              <span class="label-desc">{{ item.desc }}</span>
            </span>
          </button>
        </nav>
      </div>

      <div class="nav-footer">
        <span
          class="status-pill"
          :class="{ running: running && !stopping, stopping }"
        >
          <span class="dot"></span>
          {{ stopping ? '停止中' : running ? 'Agent 运行中' : 'Agent 空闲' }}
        </span>
        <span class="version">v0.1 · 本地部署</span>
      </div>
    </aside>

    <main class="main-panel">
      <JobsPage v-if="activePage === 'jobs'" />
      <MonitorPage v-else-if="activePage === 'monitor'" />
      <SettingsPage v-else />
    </main>
  </div>
</template>

<style scoped>
.side-nav nav button {
  flex-direction: row;
  align-items: center;
  padding: 10px 12px;
  gap: 12px;
}

.side-nav nav button .label-block {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.side-nav nav button .label-text {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.side-nav nav button .label-desc {
  font-size: 11px;
  color: var(--c-sidebar-text-muted);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.side-nav nav button.active .label-desc {
  color: rgba(255, 255, 255, 0.7);
}

.nav-footer .version {
  font-size: 11px;
  color: var(--c-sidebar-text-muted);
  text-align: center;
}
</style>
