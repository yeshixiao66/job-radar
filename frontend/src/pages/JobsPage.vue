<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getFilters, getJobs, getStatus, runAgents, stopAgents, type JobRow } from '../api'

const loading = ref(false)
const running = ref(false)
const stopping = ref(false)
const jobs = ref<JobRow[]>([])
// 后端 /api/filters 返回的真实可选值
const filterOptions = ref<Record<string, string[]>>({
  industry: [],
  company_type: [],
  batch: [],
  location: [],
  confidence: [],
  status: [],
})
const view = ref<'table' | 'card' | 'kanban'>('table')

const query = reactive({
  keyword: '',
  industry: '',
  company_type: '',
  batch: '',
  location: '',
  confidence: '',
  status: '',
})

const totalJobs = computed(() => jobs.value.length)
// 真实规则：有投递链接 = 可投递
const canApplyJobs = computed(() => jobs.value.filter((j) => !!j.apply_url).length)
const highConfidenceJobs = computed(() => jobs.value.filter((j) => j.confidence === '高').length)
const withApplyUrl = computed(() => jobs.value.filter((j) => !!j.apply_url).length)
const pendingJobs = computed(() => jobs.value.filter((j) => !j.apply_url).length)

const filterFields: { key: keyof typeof query; label: string }[] = [
  { key: 'industry', label: '行业' },
  { key: 'location', label: '城市' },
  { key: 'batch', label: '招聘对象' },
  { key: 'company_type', label: '公司类型' },
  { key: 'confidence', label: '可信度' },
  { key: 'status', label: '状态' },
]

function togglePill(field: keyof typeof query, value: string) {
  query[field] = query[field] === value ? '' : value
}

function isPillActive(field: keyof typeof query, value: string) {
  return query[field] === value
}

function stars(score: number) {
  return '★'.repeat(Math.max(1, Math.min(5, score || 1)))
}

function confidenceType(value: string) {
  if (value === '高') return 'success'
  if (value === '中高' || value === '中') return 'warning'
  return 'info'
}

function statusType(value: string) {
  if (value.includes('可投递') || value.includes('就绪')) return 'success'
  if (value.includes('待') || value.includes('缺少')) return 'warning'
  return 'info'
}

function safeUrl(value: string) {
  const raw = String(value || '').trim()
  if (!raw || raw === '#') return ''
  if (/^(mailto:|tel:|javascript:)/i.test(raw)) return ''
  if (raw.startsWith('//')) return `https:${raw}`
  if (/^https?:\/\//i.test(raw)) return raw
  if (raw.includes('.')) return `https://${raw}`
  return ''
}

function openJobLink(value: string) {
  const url = safeUrl(value)
  if (!url) {
    ElMessage.warning('链接格式无效，暂时无法打开')
    return
  }
  const opened = window.open(url, '_blank')
  if (!opened) {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.target = '_blank'
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    navigator.clipboard?.writeText(url).catch(() => undefined)
    ElMessage.warning('如果没有打开新页面，链接已复制，可粘贴到浏览器打开')
  } else {
    opened.opener = null
  }
}

async function loadJobs() {
  loading.value = true
  try {
    jobs.value = await getJobs(query)
  } catch (e: any) {
    ElMessage.error('加载失败：' + e.message)
  } finally {
    loading.value = false
  }
}

async function loadFilters() {
  try {
    filterOptions.value = await getFilters()
  } catch (e) {
    // 静默
  }
}

async function refreshStatus() {
  try {
    const status = await getStatus()
    running.value = status.running
    stopping.value = status.stopping
  } catch (e) {
    // 后端未启动
  }
}

async function startAgents() {
  if (running.value) return
  try {
    const result = await runAgents()
    ElMessage[result.ok ? 'success' : 'warning'](result.message)
    await refreshStatus()
    setTimeout(loadJobs, 1500)
  } catch (e: any) {
    ElMessage.error('启动失败：' + e.message)
  }
}

async function stopRunningAgents() {
  try {
    const result = await stopAgents()
    ElMessage[result.ok ? 'success' : 'warning'](result.message)
    await refreshStatus()
  } catch (e: any) {
    ElMessage.error('停止失败：' + e.message)
  }
}

function resetFilters() {
  Object.keys(query).forEach((k) => ((query as any)[k] = ''))
  loadJobs()
}

onMounted(async () => {
  await Promise.all([loadJobs(), loadFilters(), refreshStatus()])
})
</script>

<template>
  <!-- 顶部：搜索 + 操作 -->
  <section class="hero-card">
    <div class="hero-title">
      <div>
        <p class="eyebrow">JOB INTELLIGENCE</p>
        <h2>汇总信息表</h2>
        <p class="hero-sub">搜索公司 / 岗位 / 地点，再用下面的筛选条件缩小范围。</p>
      </div>
      <div class="head-actions">
        <el-tag :type="running ? (stopping ? 'warning' : 'success') : 'info'" size="large" effect="light">
          {{ stopping ? '停止中' : running ? 'Agent 运行中' : 'Agent 空闲' }}
        </el-tag>
        <button class="btn" @click="loadJobs">刷新</button>
        <button class="btn" :disabled="!running || stopping" @click="stopRunningAgents">停止 Agent</button>
        <button class="btn primary" :disabled="running" @click="startAgents">运行 Agent</button>
      </div>
    </div>

    <div class="search-bar">
      <input
        v-model="query.keyword"
        placeholder="搜索公司 / 岗位 / 地点 / 行业"
        @keyup.enter="loadJobs"
      />
      <button class="search-btn" @click="loadJobs">搜索</button>
    </div>
  </section>

  <!-- 筛选区：每个字段的药丸都来自后端真实数据 -->
  <section v-if="filterFields.some(f => filterOptions[f.key]?.length)" class="hero-card">
    <div v-for="field in filterFields" :key="field.key" class="filter-group">
      <span class="filter-label">{{ field.label }}：</span>
      <div class="pill-row">
        <button
          v-for="value in filterOptions[field.key]"
          :key="value"
          class="pill"
          :class="{ active: isPillActive(field.key, value) }"
          @click="togglePill(field.key, value); loadJobs()"
        >
          {{ value }}
          <span v-if="isPillActive(field.key, value)" class="x">×</span>
        </button>
        <span v-if="!filterOptions[field.key]?.length" class="muted" style="font-size: 12px;">暂无</span>
      </div>
    </div>
  </section>

  <!-- 汇总指标 -->
  <section class="summary-strip">
    <div>
      <span class="label">岗位记录</span>
      <strong>{{ totalJobs }}</strong>
      <div class="trend">当前已入库</div>
    </div>
    <div>
      <span class="label">可投递</span>
      <strong>{{ canApplyJobs }}</strong>
      <div class="trend">有投递链接</div>
    </div>
    <div>
      <span class="label">待补链接</span>
      <strong>{{ pendingJobs }}</strong>
      <div class="trend">缺投递入口</div>
    </div>
    <div>
      <span class="label">高可信</span>
      <strong>{{ highConfidenceJobs }}</strong>
      <div class="trend">confidence=高</div>
    </div>
  </section>

  <!-- 表头操作 -->
  <div class="table-meta">
    <div class="count">共 <strong>{{ totalJobs }}</strong> 条</div>
    <div class="flex gap-2" style="align-items: center;">
      <span class="muted" style="font-size: 12px;">视图：</span>
      <div class="view-toggle">
        <button :class="{ active: view === 'table' }" @click="view = 'table'">表格</button>
        <button :class="{ active: view === 'card' }" @click="view = 'card'">卡片</button>
        <button :class="{ active: view === 'kanban' }" @click="view = 'kanban'">看板</button>
      </div>
      <button class="btn sm" @click="resetFilters">重置筛选</button>
    </div>
  </div>

  <!-- 表格视图 -->
  <section v-if="view === 'table'" class="table-card">
    <el-table v-loading="loading" :data="jobs" stripe>
      <el-table-column prop="publish_date" label="发布日期" min-width="110" />
      <el-table-column prop="company_name" label="公司名称" min-width="140">
        <template #default="{ row }">
          <strong style="color: var(--c-text);">{{ row.company_name }}</strong>
        </template>
      </el-table-column>
      <el-table-column label="行业" min-width="120">
        <template #default="{ row }">
          <span class="badge industry">{{ row.industry || '未分类' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="job_title" label="岗位" min-width="220" show-overflow-tooltip />
      <el-table-column prop="location" label="地点" min-width="100" show-overflow-tooltip />
      <el-table-column label="类型" min-width="100">
        <template #default="{ row }">
          <span class="badge soft">{{ row.source_type || '官方' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="招聘对象" min-width="120">
        <template #default="{ row }">
          <span class="badge">{{ row.batch || '不限' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公告" min-width="90">
        <template #default="{ row }">
          <button v-if="safeUrl(row.announcement_url)" class="badge badge-link link-button" :title="safeUrl(row.announcement_url)" @click.stop="openJobLink(row.announcement_url)">公告</button>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="投递" min-width="90">
        <template #default="{ row }">
          <button v-if="safeUrl(row.apply_url)" class="badge badge-link link-button" :title="safeUrl(row.apply_url)" @click.stop="openJobLink(row.apply_url)">投递</button>
          <span v-else class="muted">待补</span>
        </template>
      </el-table-column>
      <el-table-column label="热度" min-width="100">
        <template #default="{ row }">
          <span class="stars">{{ stars(row.hot_score) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="可信度" min-width="100">
        <template #default="{ row }">
          <el-tag :type="confidenceType(row.confidence)" size="small">{{ row.confidence }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新" min-width="120">
        <template #default="{ row }">
          <span class="muted">{{ row.last_updated?.slice(5, 16) || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!loading && jobs.length === 0" class="empty-state">
      <div class="icon">📭</div>
      <div class="title">还没有岗位记录</div>
      <div>调整筛选条件，或点击右上角「运行 Agent」开始抓取</div>
    </div>
  </section>

  <!-- 卡片视图 -->
  <section v-else-if="view === 'card'" class="agent-grid">
    <article v-for="job in jobs" :key="job.id" class="agent-card">
      <h3>
        <span>{{ job.company_name }}</span>
        <el-tag :type="statusType(job.status)" size="small">{{ job.status }}</el-tag>
      </h3>
      <p class="last-msg">{{ job.job_title }}</p>
      <div class="agent-meta">
        <span class="meta-item badge industry">{{ job.industry || '未分类' }}</span>
        <span class="meta-item">📍 {{ job.location || '不限' }}</span>
        <span class="meta-item stars">{{ stars(job.hot_score) }}</span>
        <span class="meta-item" style="margin-left: auto;">
          <button v-if="safeUrl(job.apply_url)" class="badge badge-link link-button" :title="safeUrl(job.apply_url)" @click.stop="openJobLink(job.apply_url)">投递</button>
        </span>
      </div>
    </article>
  </section>

  <!-- 看板视图：按"有投递链接"分两栏 -->
  <section v-else class="agent-grid">
    <div class="card" style="padding: 0;">
      <div class="card-head">
        <h3>可投递</h3>
        <span class="meta">{{ canApplyJobs }} 条</span>
      </div>
      <div class="card-body" style="padding: 12px;">
        <article v-for="job in jobs.filter(j => j.apply_url)" :key="job.id" class="agent-card" style="margin-bottom: 10px;">
          <h3><span>{{ job.company_name }}</span><span class="stars">{{ stars(job.hot_score) }}</span></h3>
          <p class="last-msg">{{ job.job_title }}</p>
          <div class="agent-meta">
            <span class="meta-item badge industry">{{ job.industry }}</span>
            <button class="badge badge-link link-button" :title="safeUrl(job.apply_url)" @click.stop="openJobLink(job.apply_url)">投递</button>
          </div>
        </article>
        <div v-if="canApplyJobs === 0" class="muted" style="padding: 16px; text-align: center; font-size: 12px;">暂无</div>
      </div>
    </div>
    <div class="card" style="padding: 0;">
      <div class="card-head">
        <h3>待补链接</h3>
        <span class="meta">{{ pendingJobs }} 条</span>
      </div>
      <div class="card-body" style="padding: 12px;">
        <article v-for="job in jobs.filter(j => !j.apply_url)" :key="job.id" class="agent-card" style="margin-bottom: 10px;">
          <h3><span>{{ job.company_name }}</span><el-tag type="warning" size="small">待补</el-tag></h3>
          <p class="last-msg">{{ job.job_title }}</p>
          <div class="agent-meta">
            <span class="meta-item badge industry">{{ job.industry }}</span>
            <button v-if="safeUrl(job.announcement_url)" class="badge badge-link link-button" :title="safeUrl(job.announcement_url)" @click.stop="openJobLink(job.announcement_url)">看公告</button>
          </div>
        </article>
        <div v-if="pendingJobs === 0" class="muted" style="padding: 16px; text-align: center; font-size: 12px;">暂无</div>
      </div>
    </div>
  </section>
</template>
