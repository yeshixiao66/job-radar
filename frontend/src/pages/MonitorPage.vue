<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getEvents,
  getLogs,
  getSources,
  getStatus,
  runAgents,
  stopAgents,
  type AgentEvent,
  type AgentLog,
  type AgentStatus,
} from '../api'

const running = ref(false)
const stopping = ref(false)
const agents = ref<AgentStatus[]>([])
const logs = ref<AgentLog[]>([])
const events = ref<AgentEvent[]>([])
const sources = ref<any[]>([])
const selectedAgent = ref('')
const logLevel = ref<'all' | 'info' | 'error'>('all')
let timer: number | undefined

const filteredLogs = ref<AgentLog[]>([])
const systemStatus = computed(() => agents.value.find((agent) => agent.agent === 'System'))
const runtimeLabel = computed(() => {
  if (stopping.value) return '停止中'
  if (running.value) return '运行中'
  if (systemStatus.value?.status === '完成') return '已完成'
  return '空闲'
})
const runtimeTagType = computed(() => {
  if (stopping.value) return 'warning'
  if (running.value) return 'success'
  if (systemStatus.value?.status === '完成') return 'success'
  return 'info'
})

async function refresh() {
  const status = await getStatus()
  running.value = status.running
  stopping.value = status.stopping
  agents.value = status.agents
  logs.value = await getLogs()
  events.value = await getEvents(selectedAgent.value)
  sources.value = await getSources()
  applyLogFilter()
}

function applyLogFilter() {
  if (logLevel.value === 'all') {
    filteredLogs.value = logs.value
  } else {
    filteredLogs.value = logs.value.filter((l) => l.level === logLevel.value)
  }
}

async function startAgents() {
  if (running.value) return
  const result = await runAgents()
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
  await refresh()
}

async function stopRunningAgents() {
  const result = await stopAgents()
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
  await refresh()
}

async function selectAgent(agent: string) {
  selectedAgent.value = selectedAgent.value === agent ? '' : agent
  events.value = await getEvents(selectedAgent.value)
}

function statusType(s: string) {
  if (s === '失败' || s.includes('错误')) return 'danger'
  if (s === '停止中' || s === '运行中' || s === '等待') return 'warning'
  return 'success'
}

onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 2500)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <section class="hero-card">
    <div class="hero-title">
      <div>
        <p class="eyebrow">RUNTIME CONSOLE</p>
        <h2>Agent 信息</h2>
        <p class="hero-sub">查看每个 Agent 的运行状态、来源、明细事件和日志。</p>
      </div>
      <div class="head-actions">
        <el-tag :type="runtimeTagType" size="large" effect="light">
          {{ runtimeLabel }}
        </el-tag>
        <button class="btn" @click="refresh">刷新</button>
        <button class="btn" :disabled="!running || stopping" @click="stopRunningAgents">停止 Agent</button>
        <button class="btn primary" :disabled="running" @click="startAgents">运行 Agent</button>
      </div>
    </div>
  </section>

  <section class="metric-grid">
    <div class="metric-card">
      <span class="label">招聘源</span>
      <strong>{{ sources.length }}</strong>
      <div class="sub">启用的来源数量</div>
    </div>
    <div class="metric-card">
      <span class="label">Agent 数量</span>
      <strong>{{ agents.length }}</strong>
      <div class="sub">已注册的 Agent</div>
    </div>
    <div class="metric-card">
      <span class="label">最近日志</span>
      <strong>{{ logs.length }}</strong>
      <div class="sub">实时滚动更新</div>
    </div>
  </section>

  <section class="agent-grid">
    <article
      v-for="agent in agents"
      :key="agent.agent"
      class="agent-card"
      :class="{ selected: selectedAgent === agent.agent }"
      @click="selectAgent(agent.agent)"
    >
      <h3>
        <span>{{ agent.agent }}</span>
        <el-tag :type="statusType(agent.status)" size="small">{{ agent.status }}</el-tag>
      </h3>
      <p class="last-msg">{{ agent.last_message || '等待执行' }}</p>
      <div class="agent-meta">
        <span class="meta-item">⏱ {{ agent.latency_ms }} ms</span>
        <span class="meta-item">✅ {{ agent.success_count }}</span>
        <span class="meta-item">❌ {{ agent.failure_count }}</span>
        <span class="meta-item" style="margin-left: auto; color: var(--c-text-muted);">
          {{ agent.updated_at?.slice(11, 19) || '' }}
        </span>
      </div>
    </article>
  </section>

  <section class="table-card" style="margin-bottom: 16px;">
    <div class="table-meta">
      <div class="count">Agent 明细 <strong style="margin-left: 4px;">{{ selectedAgent ? `- ${selectedAgent}` : '- 全部' }}</strong></div>
      <div class="muted" style="font-size: 12px;">{{ events.length }} 条</div>
    </div>
    <el-table :data="events" stripe>
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="agent" label="Agent" width="150" />
      <el-table-column prop="source_name" label="来源" width="180" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === '失败' ? 'danger' : 'success'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="latency_ms" label="耗时(ms)" width="110" />
      <el-table-column prop="message" label="消息" min-width="200" show-overflow-tooltip />
      <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip />
    </el-table>
  </section>

  <section class="table-card">
    <div class="table-meta">
      <div class="count">运行日志 <strong style="margin-left: 4px;">{{ filteredLogs.length }} 条</strong></div>
      <div class="view-toggle">
        <button :class="{ active: logLevel === 'all' }" @click="logLevel = 'all'; applyLogFilter()">全部</button>
        <button :class="{ active: logLevel === 'info' }" @click="logLevel = 'info'; applyLogFilter()">信息</button>
        <button :class="{ active: logLevel === 'error' }" @click="logLevel = 'error'; applyLogFilter()">错误</button>
      </div>
    </div>
    <el-table :data="filteredLogs" stripe>
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="agent" label="Agent" width="150" />
      <el-table-column label="级别" width="100">
        <template #default="{ row }">
          <el-tag :type="row.level === 'error' ? 'danger' : 'info'" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="latency_ms" label="耗时(ms)" width="110" />
      <el-table-column prop="message" label="消息" min-width="280" show-overflow-tooltip />
    </el-table>
  </section>
</template>
