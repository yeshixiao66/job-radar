<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  activateSettings,
  deleteSettings,
  getLlmStatus,
  getSettings,
  saveSettings,
  testLlm,
  type ApiSettings,
  type LlmStatus,
} from '../api'

const loading = ref(false)
const saving = ref(false)
const profiles = ref<ApiSettings['profiles']>([])
const activeProfile = ref('')
const llmStatus = ref<LlmStatus | null>(null)
const editing = ref(false)
const editingOriginalName = ref('')
const testing = ref(false)
let llmTimer: number | undefined

const form = reactive({
  profile_name: '',
  api_key: '',
  base_url: '',
  model: '',
})

function applySettings(settings: ApiSettings) {
  profiles.value = settings.profiles || []
  activeProfile.value = settings.active_profile || settings.profile_name
  if (!editing.value) {
    resetForm()
  }
}

function currentProfile() {
  return profiles.value.find((item) => item.name === activeProfile.value)
}

async function load() {
  loading.value = true
  try {
    const settings = await getSettings()
    applySettings(settings)
    await refreshLlmStatus()
  } finally {
    loading.value = false
  }
}

async function refreshLlmStatus() {
  llmStatus.value = await getLlmStatus()
}

async function save() {
  if (!form.profile_name.trim()) {
    ElMessage.warning('请先填写配置名称')
    return
  }
  if (!form.base_url.trim() || !form.model.trim()) {
    ElMessage.warning('请填写 Base URL 和 Model')
    return
  }
  saving.value = true
  try {
    const settings = await saveSettings({
      profile_name: form.profile_name,
      original_name: editingOriginalName.value,
      api_key: form.api_key,
      base_url: form.base_url,
      model: form.model,
    })
    applySettings(settings)
    resetForm()
    await refreshLlmStatus()
    ElMessage.success('API 配置已保存并设为当前使用')
  } finally {
    saving.value = false
  }
}

function selectProfile(name: string) {
  const profile = profiles.value.find((item) => item.name === name)
  if (!profile) return
  editing.value = true
  editingOriginalName.value = profile.name
  form.profile_name = profile.name
  form.base_url = profile.base_url
  form.model = profile.model
  form.api_key = ''
}

async function activateProfile(name: string) {
  const settings = await activateSettings(name)
  applySettings(settings)
  await refreshLlmStatus()
  ElMessage.success(`已切换到 ${name}`)
}

async function deleteProfile(name: string) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${name}」吗？删除后不会显示完整 API Key，无法从页面恢复。`,
      '删除 API 配置',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  const settings = await deleteSettings(name)
  applySettings(settings)
  if (editingOriginalName.value === name) {
    resetForm()
  }
  await refreshLlmStatus()
  ElMessage.success(`已删除 ${name}`)
}

async function runLlmTest() {
  testing.value = true
  try {
    const result = await testLlm()
    ElMessage[result.ok ? 'success' : 'warning'](result.message)
    await refreshLlmStatus()
  } finally {
    testing.value = false
  }
}

function newProfile() {
  editing.value = true
  editingOriginalName.value = ''
  form.profile_name = ''
  form.api_key = ''
  form.base_url = ''
  form.model = ''
}

function resetForm() {
  editing.value = false
  editingOriginalName.value = ''
  form.profile_name = ''
  form.api_key = ''
  form.base_url = ''
  form.model = ''
}

onMounted(() => {
  load()
  llmTimer = window.setInterval(refreshLlmStatus, 5000)
})

onUnmounted(() => {
  if (llmTimer) window.clearInterval(llmTimer)
})
</script>

<template>
  <section class="hero-card">
    <div class="hero-title">
      <div>
        <p class="eyebrow">MODEL GATEWAY</p>
        <h2>API 配置管理</h2>
        <p class="hero-sub">管理 Extractor Agent 和 Classifier Agent 使用的 LLM 接口。</p>
      </div>
      <div class="head-actions">
        <button class="btn" @click="load">刷新</button>
        <button class="btn primary" @click="newProfile">新增配置</button>
      </div>
    </div>
  </section>

  <section v-loading="loading" class="settings-card">
    <h3>当前配置</h3>
    <p class="desc">当前生效配置只展示，不显示完整 API Key。</p>

    <div class="form-grid">
      <div>
        <span class="label">配置名称</span>
        <div class="form-hint" style="margin-top: 8px;">{{ currentProfile()?.name || activeProfile || '未选择' }}</div>
      </div>
      <div class="full">
        <span class="label">API Key</span>
        <div class="form-hint" style="margin-top: 8px;">
          <span v-if="currentProfile()?.api_key_set" class="badge success">{{ currentProfile()?.api_key_preview }}</span>
          <span v-else class="badge soft">未保存 API Key</span>
        </div>
      </div>
      <div>
        <span class="label">Base URL</span>
        <div class="form-hint" style="margin-top: 8px;">{{ currentProfile()?.base_url || '未配置' }}</div>
      </div>
      <div>
        <span class="label">Model</span>
        <div class="form-hint" style="margin-top: 8px;">{{ currentProfile()?.model || '未配置' }}</div>
      </div>
    </div>
  </section>

  <section class="table-card" style="margin-bottom: 16px;">
    <div class="table-meta">
      <div class="count">LLM 使用状态</div>
      <div class="head-actions">
        <button class="btn sm" @click="refreshLlmStatus">刷新</button>
        <button class="btn sm primary" :disabled="testing" @click="runLlmTest">测试 LLM</button>
      </div>
    </div>
    <div class="form-grid" style="padding: 4px 2px 2px;">
      <div>
        <span class="label">调用 Agent</span>
        <div style="margin-top: 8px;">
          <span v-for="agent in llmStatus?.used_by || []" :key="agent" class="badge" style="margin-right: 6px;">
            {{ agent }}
          </span>
        </div>
      </div>
      <div>
        <span class="label">当前接口</span>
        <div class="form-hint" style="margin-top: 8px;">
          {{ llmStatus?.api_key_set ? '已配置 Key' : '未配置 Key' }} · {{ llmStatus?.base_url || '未配置 Base URL' }} · {{ llmStatus?.model || '未配置 Model' }}
        </div>
      </div>
      <div class="full">
        <span class="label">最近 LLM 消息</span>
        <div class="form-hint" style="margin-top: 8px;">
          {{ llmStatus?.last_message || '暂无 LLM 调用记录' }}
          <span v-if="llmStatus?.last_time"> · {{ llmStatus.last_time }}</span>
        </div>
      </div>
    </div>
  </section>

  <section class="table-card">
    <div class="table-meta">
      <div class="count">已保存配置 <strong style="margin-left: 4px;">{{ profiles.length }} 个</strong></div>
      <div class="muted" style="font-size: 12px;">可编辑名称、Base URL、Model 和 API Key</div>
    </div>
    <div v-if="editing" class="settings-card" style="margin: 0 0 16px; box-shadow: none;">
      <h3>{{ editingOriginalName ? '编辑配置' : '新增配置' }}</h3>
      <div class="form-grid">
        <div>
          <el-form-item label="配置名称">
            <el-input v-model="form.profile_name" placeholder="例如：BearLab / DeepSeek / 备用 API" />
          </el-form-item>
        </div>
        <div>
          <el-form-item label="API Key">
            <el-input
              v-model="form.api_key"
              type="password"
              show-password
              :placeholder="editingOriginalName ? '留空表示继续使用原 Key' : '请输入 API Key'"
            />
          </el-form-item>
        </div>
        <div>
          <el-form-item label="Base URL">
            <el-input v-model="form.base_url" placeholder="例如：https://api.example.com/v1" />
          </el-form-item>
        </div>
        <div>
          <el-form-item label="Model">
            <el-input v-model="form.model" placeholder="例如：deepseek-chat / qwen-plus / gpt-4o-mini" />
          </el-form-item>
        </div>
      </div>
      <div class="head-actions" style="justify-content: flex-end;">
        <button v-if="editingOriginalName" class="btn danger" @click="deleteProfile(editingOriginalName)">删除配置</button>
        <button class="btn" @click="resetForm">取消</button>
        <button class="btn primary" :disabled="saving" @click="save">保存配置</button>
      </div>
    </div>
    <el-table :data="profiles" empty-text="还没有保存过 API 配置">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="base_url" label="Base URL" min-width="240" show-overflow-tooltip />
      <el-table-column prop="model" label="Model" min-width="180" show-overflow-tooltip />
      <el-table-column label="Key" width="150">
        <template #default="{ row }">
          <span v-if="row.api_key_set" class="badge">{{ row.api_key_preview }}</span>
          <span v-else class="muted">未保存</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <span v-if="row.name === activeProfile" class="badge success">当前使用</span>
          <span v-else class="badge muted">备用</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <button class="btn sm" @click="selectProfile(row.name)">编辑</button>
          <button
            class="btn sm primary"
            style="margin-left: 6px;"
            :disabled="row.name === activeProfile"
            @click="activateProfile(row.name)"
          >启用</button>
          <button
            class="btn sm danger"
            style="margin-left: 6px;"
            @click="deleteProfile(row.name)"
          >删除</button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>
