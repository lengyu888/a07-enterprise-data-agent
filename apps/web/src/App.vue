<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

type ReadyPayload = {
  status: string
  dependencies: {
    database: string
    deepseek: string
  }
}

type BootstrapPayload = {
  project: string
  edition: string
  phase: string
  architecture: string[]
  core_innovation: string[]
  next_milestone: string
}

const ready = ref<ReadyPayload | null>(null)
const bootstrap = ref<BootstrapPayload | null>(null)
const loading = ref(true)
const error = ref('')

const systemReady = computed(() => ready.value?.status === 'ready')

async function loadStatus() {
  loading.value = true
  error.value = ''

  try {
    const [readyResponse, bootstrapResponse] = await Promise.all([
      fetch('/api/ready'),
      fetch('/api/v1/system/bootstrap'),
    ])

    if (!readyResponse.ok || !bootstrapResponse.ok) {
      throw new Error('服务尚未就绪')
    }

    ready.value = (await readyResponse.json()) as ReadyPayload
    bootstrap.value = (await bootstrapResponse.json()) as BootstrapPayload
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取系统状态'
  } finally {
    loading.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <main class="shell">
    <div class="blueprint" aria-hidden="true"></div>

    <header class="masthead">
      <div class="mark" aria-label="项目编号 A07">A<span>07</span></div>
      <div class="masthead-copy">
        <p class="eyebrow">浙江省大学生服务外包创新应用大赛 · COMPETITION BUILD</p>
        <h1>企业数据底座<br /><em>智能问析 Agent</em></h1>
      </div>
      <div class="phase-stamp">
        <span>BUILD PHASE</span>
        <strong>{{ bootstrap?.phase ?? '00' }}</strong>
      </div>
    </header>

    <section class="status-rail" aria-live="polite">
      <div class="signal" :class="{ active: systemReady }"></div>
      <div>
        <span class="label">SYSTEM STATE</span>
        <strong v-if="loading">正在连接本地数据底座…</strong>
        <strong v-else-if="error" class="error">{{ error }}</strong>
        <strong v-else>{{ systemReady ? '本地工程基座已就绪' : '依赖尚未就绪' }}</strong>
      </div>
      <button type="button" :disabled="loading" @click="loadStatus">重新检测</button>
    </section>

    <section class="grid">
      <article class="panel hero-panel">
        <div class="panel-index">01 / FOUNDATION</div>
        <p class="lead">
          这一阶段只回答一个问题：<b>工程是否能被任何成员稳定构建、启动和检查？</b>
          Agent 能力将在可验证的底座上逐步生长，而不是一次性堆叠。
        </p>
        <div class="stack-line">
          <span v-for="item in bootstrap?.architecture ?? ['Vue 3', 'FastAPI', 'PostgreSQL']" :key="item">
            {{ item }}
          </span>
        </div>
      </article>

      <article class="panel metric-panel">
        <div class="panel-index">DEPENDENCIES</div>
        <dl>
          <div>
            <dt>PostgreSQL / pgvector</dt>
            <dd :class="ready?.dependencies.database">{{ ready?.dependencies.database ?? 'checking' }}</dd>
          </div>
          <div>
            <dt>DeepSeek API</dt>
            <dd :class="ready?.dependencies.deepseek">{{ ready?.dependencies.deepseek ?? 'checking' }}</dd>
          </div>
          <div>
            <dt>Delivery profile</dt>
            <dd>3 CONTAINERS</dd>
          </div>
        </dl>
      </article>

      <article class="panel innovation-panel">
        <div class="panel-index">CORE / KEEP</div>
        <ul>
          <li v-for="(item, index) in bootstrap?.core_innovation ?? []" :key="item">
            <span>0{{ index + 1 }}</span>{{ item }}
          </li>
        </ul>
      </article>

      <article class="panel next-panel">
        <div class="panel-index">NEXT MILESTONE</div>
        <h2>{{ bootstrap?.next_milestone ?? '加载阶段信息' }}</h2>
        <p>表、字段、样例、关系与制造业指标，将成为后续 RAG 和 Text-to-SQL 的真实语义依据。</p>
        <div class="progress" aria-label="阶段进度 1/8">
          <i></i>
        </div>
        <small>01 OF 08 · LOCAL CONFIRMATION REQUIRED</small>
      </article>
    </section>

    <footer>
      <span>Contest Edition / Local Development</span>
      <span>模型规划 · 工具执行 · 结果有据</span>
    </footer>
  </main>
</template>

