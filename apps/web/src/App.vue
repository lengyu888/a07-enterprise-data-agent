<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

type ReadyPayload = { status: string; dependencies: { database: string; deepseek: string } }
type BootstrapPayload = { phase: string; next_milestone: string }
type DeepSeekConfigStatus = {
  configured: boolean; status: string; source: 'runtime' | 'none'
  model: string; base_url: string; reasoning_effort: string; runtime_only: boolean; can_clear: boolean; verified?: boolean
}
type CatalogSummary = { table_count: number; column_count: number; relation_count: number; total_rows: number; refreshed_at: string; dataset_max_business_date: string }
type CatalogTable = { id: number; schema_name: string; table_name: string; display_name: string; description: string; business_domain: string; row_count: number; column_count: number }
type CatalogColumn = { id: number; column_name: string; data_type: string; is_nullable: boolean; is_primary_key: boolean; description: string; sample_values: unknown[] }
type TableDetail = CatalogTable & { columns: CatalogColumn[] }
type Relation = { id: number; source_table: string; source_column: string; target_table: string; target_column: string; cardinality: string }
type Topic = { topic_code: string; topic_name: string; description: string; accent_color: string; metric_count: number; rule_count: number; object_count: number }
type Rule = { rule_code: string; topic_code: string; rule_name: string; rule_content: string }
type Synonym = { topic_code: string; canonical_term: string; synonym_term: string }
type Metric = { metric_code: string; topic_code: 'quality' | 'equipment' | 'production'; metric_name: string; description: string; formula: string; unit: string; grain: string; dimensions: string[]; mapped_tables: string[]; owner_name: string; version: string; status: 'draft' | 'published' | 'disabled' }
type AgentTrace = { node_name: string; display_name: string; status: string; duration_ms: number; summary: string; payload: Record<string, unknown> }
type AgentRun = {
  run_id: string; status: 'completed'; question: string; model: string; generation_mode: string; duration_ms: number
  time_range: { start: string; end: string; anchor: string }; plan: string[]
  evidence: { metric: { code: string; name: string; formula: string; version: string }; rule: string; rules: Array<Record<string, string>>; tables: string[]; relations: Array<{ source_table: string; source_column: string; target_table: string; target_column: string }>; items: Array<{ id: number; source_type: string; source_id: string; title: string; score: number; channels: string[] }>; retrieval: { strategy: string; top_k: number; channel_hits: Record<string, number>; context_reduction_pct: number } }
  sql: { text: string; validation: string; repair_count: number; referenced_tables: string[] }
  result: { columns: string[]; rows: Array<Record<string, string | number>>; row_count: number }
  chart: { type: string; title: string; x_field: string; y_field: string; unit: string; categories: string[]; series: Array<{ name: string; data: number[] }> }
  answer: string; trace: AgentTrace[]
}

type QualityBrief = {
  run_id: string; status: string; duration_ms: number
  period: { start: string; end: string; anchor: string; previous_month: string }
  assessment: {
    current_yield: number; previous_yield: number; yield_delta_pp: number; inspected_qty: number; unqualified_qty: number; status: string
    worst_process: { process_name: string; yield_rate: number; inspected_qty: number }
    top_defect: { defect_type: string; defect_count: number; defect_share: number; cumulative_share: number }
    vital_few: string[]
  }
  brief: { headline: string; summary: string; risks: string[]; actions: string[]; generation_mode: string }
  charts: {
    process: Array<{ process_name: string; yield_rate: number; inspected_qty: number }>
    pareto: Array<{ defect_type: string; defect_count: number; defect_share: number; cumulative_share: number }>
    trend: Array<{ business_date: string; yield_rate: number }>
  }
  evidence: Array<{ question: string; metric: string; metric_code: string; formula: string; tables: string[]; top_sources: string[] }>
  trace: AgentTrace[]
}

type EquipmentDiagnosis = {
  run_id: string; status: string; duration_ms: number
  period: { training: string; scoring: string; anchor: string }
  recipe: { code: string; name: string; algorithm: string; version: string; features: string[]; parameters: Record<string, number>; feature_sql: string; explanation_rule: string }
  assessment: { top_equipment: EquipmentRank; top_anomaly_date: string; top_anomaly_score: number; anomaly_rate_pct: number; status: string }
  ranking: EquipmentRank[]
  timeline: Array<{ business_date: string; anomaly_score: number; is_anomaly: boolean; downtime_minutes: number }>
  deviations: Array<{ feature: string; label: string; current: number; baseline_median: number; robust_deviation: number; change_pct: number | null }>
  reason_distribution: Array<{ event_reason: string; event_count: number; duration_minutes: number }>
  brief: { headline: string; summary: string; risks: string[]; actions: string[]; generation_mode: string }
  evidence: { metric: string; formula: string; tables: string[]; rules: string[]; retrieval: { strategy: string; context_reduction_pct: number }; sources: string[] }
  trace: AgentTrace[]
}
type EquipmentRank = { equipment_id: string; equipment_name: string; equipment_type: string; line_name: string; anomaly_days: number; max_anomaly_score: number; total_downtime_minutes: number; max_single_duration: number; alarm_count: number }

type ProductionTrend = {
  run_id: string; status: string; duration_ms: number
  period: { start: string; end: string; anchor: string; trend_window: string }
  recipe: { code: string; name: string; algorithm: string; version: string; features: string[]; parameters: Record<string, number | string>; feature_sql: string; explanation_rule: string }
  assessment: { final_output: number; planned_qty: number; plan_attainment: number; best_line: ProductionLine; attention_line: ProductionLine; rising_lines: number; declining_lines: number; status: string; trend_disclaimer: string }
  ranking: ProductionLine[]
  daily_trend: Array<{ business_date: string; final_output: number; planned_qty: number; plan_attainment: number }>
  line_trends: Array<{ line_id: string; line_name: string; window_start: string; window_end: string; slope_per_day: number; direction: string; start_output: number; end_output: number; series: Array<{ business_date: string; final_output: number }> }>
  brief: { headline: string; summary: string; observations: string[]; actions: string[]; generation_mode: string }
  evidence: { metrics: Array<{ code: string; name: string; formula: string; version: string }>; tables: string[]; rules: string[]; sources: string[]; retrieval: Array<{ strategy: string; context_reduction_pct: number }> }
  trace: AgentTrace[]
}
type ProductionLine = { line_id: string; line_name: string; final_output: number; planned_qty: number; plan_attainment: number; slope_per_day: number; direction: string }
type AlgorithmSuite = {
  run_id: string; status: string; algorithm_count: number; passed_count: number; duration_ms: number
  algorithms: Array<{ algorithm: string; scene: string; use_case: string; status: string; rows: { training: number; validation: number }; metrics: Record<string, number>; boundary: string }>
  guardrail: string
}
type AgentClarification = {
  status: 'needs_clarification'; clarification_id: string; question: string; detected_scene: string | null
  missing_fields: string[]; prompt: string; options: Array<{ label: string; question: string }>; trace: AgentTrace[]
}
type EvaluationMetric = {
  key: string; label: string; value: number; unit: string; threshold: number
  direction: 'gte' | 'lte'; passed: boolean; description: string
}
type EvaluationOverview = {
  generated_at: string
  window: { runs: number; limit: number; completed: number; failed: number }
  summary: { passed_gates: number; total_gates: number; status: 'ready' | 'attention' | 'insufficient_data' }
  metrics: EvaluationMetric[]
  rag: { case_count: number; passed_cases: number; case_pass_pct: number; required_table_recall_pct: number; metric_accuracy_pct: number; top_k: number; cases: Array<{ case_code: string; scene: string; question: string; metric_ok: boolean; expected_tables: string[]; recalled_tables: string[]; passed: boolean }> }
  clarification: { total: number; resolved: number; pending: number; resolution_pct: number }
  recent_runs: Array<{ run_id: string; question: string; scene: string; status: string; model_id: string; duration_ms: number; repair_count: number; evidence_complete: boolean; started_at: string }>
  methodology: string
}

type ViewName = 'overview' | 'catalog' | 'knowledge' | 'quality' | 'equipment' | 'production' | 'agent' | 'evaluation' | 'settings'
type OverviewSlide = {
  id: Exclude<ViewName, 'overview'>
  module: string
  code: string
  title: string
  highlight: string
  description: string
  action: string
  backdrop: string
  accent: string
}

const activeView = ref<ViewName>('overview')
const ready = ref<ReadyPayload | null>(null)
const bootstrap = ref<BootstrapPayload | null>(null)
const deepseekConfig = ref<DeepSeekConfigStatus | null>(null)
const deepseekApiKey = ref('')
const deepseekSelectedModel = ref('deepseek-v4-pro')
const deepseekConfigSaving = ref(false)
const deepseekConfigError = ref('')
const deepseekConfigMessage = ref('')
const showDeepseekApiKey = ref(false)
const summary = ref<CatalogSummary | null>(null)
const tables = ref<CatalogTable[]>([])
const relations = ref<Relation[]>([])
const tableDetail = ref<TableDetail | null>(null)
const topics = ref<Topic[]>([])
const rules = ref<Rule[]>([])
const synonyms = ref<Synonym[]>([])
const metrics = ref<Metric[]>([])
const selectedDomain = ref('全部')
const selectedTopic = ref('all')
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const metricEditorOpen = ref(false)
const editingMetric = ref(false)
const metricSaving = ref(false)
const metricError = ref('')
const dimensionText = ref('')
const mappedTableText = ref('')
const agentQuestion = ref('分析本月各工序良率，找出良率最低的工序')
const agentRunning = ref(false)
const agentError = ref('')
const agentResult = ref<AgentRun | null>(null)
const agentClarification = ref<AgentClarification | null>(null)
const pendingClarificationId = ref<string | null>(null)
const exportMessage = ref('')
const qualityBrief = ref<QualityBrief | null>(null)
const qualityBriefRunning = ref(false)
const qualityBriefError = ref('')
const equipmentDiagnosis = ref<EquipmentDiagnosis | null>(null)
const equipmentRunning = ref(false)
const equipmentError = ref('')
const productionTrend = ref<ProductionTrend | null>(null)
const productionRunning = ref(false)
const productionError = ref('')
const algorithmSuite = ref<AlgorithmSuite | null>(null)
const algorithmRunning = ref(false)
const algorithmError = ref('')
const evaluation = ref<EvaluationOverview | null>(null)
const evaluationLoading = ref(false)
const evaluationError = ref('')
const deepseekModels = [
  { id: 'deepseek-v4-pro', name: 'V4 Pro', tag: 'DEEP REASONING', description: '复杂 Text-to-SQL、分析规划与管理简报' },
  { id: 'deepseek-v4-flash', name: 'V4 Flash', tag: 'FAST RESPONSE', description: '快速演示、重复问析与低等待交互' },
]
const overviewSlides: OverviewSlide[] = [
  { id: 'catalog', module: '数据目录', code: 'MODULE 02 / LIVE DATA CATALOG', title: '让数据资产', highlight: '先被看懂', description: '自动扫描 PostgreSQL 表、字段、样例与真实外键，让后续问析从可信的数据结构出发。', action: '打开数据目录', backdrop: 'DATA', accent: '#2457ff' },
  { id: 'knowledge', module: '业务知识', code: 'MODULE 03 / SEMANTIC KNOWLEDGE', title: '把业务口径', highlight: '交给 Agent', description: '统一管理指标公式、业务规则、同义词与映射关系，为 RAG 和 Text-to-SQL 提供可审核语义。', action: '打开业务知识', backdrop: 'RULE', accent: '#ff5a36' },
  { id: 'quality', module: '质量分析', code: 'MODULE 04 / QUALITY INTELLIGENCE', title: '把质量波动', highlight: '追到证据', description: '将良率环比、工序短板、缺陷 Pareto 与每日趋势组织成可下钻、可复核的质量分析闭环。', action: '打开质量驾驶舱', backdrop: 'QUALITY', accent: '#2457ff' },
  { id: 'equipment', module: '设备异常', code: 'MODULE 05 / EQUIPMENT ANOMALY', title: '别等停机', highlight: '先看偏离', description: '通过固定特征 Recipe 与 Isolation Forest 识别设备行为偏离，再由 DeepSeek 组织核查线索。', action: '打开设备诊断', backdrop: 'SIGNAL', accent: '#087ea4' },
  { id: 'production', module: '生产趋势', code: 'MODULE 06 / PRODUCTION TREND', title: '把计划差距', highlight: '变成行动线索', description: '审核 Recipe 将末工序口径、计划达成率、七日线性趋势与 DeepSeek 简报连成可复现生产问析链。', action: '打开生产趋势', backdrop: 'TREND', accent: '#2457ff' },
  { id: 'agent', module: '智能问析', code: 'MODULE 07 / AGENT ANALYSIS', title: '把自然语言', highlight: '变成可靠分析', description: 'DeepSeek 规划、混合 RAG、受控 Text-to-SQL、安全执行与动态图表共同形成有据可查的答案。', action: '启动智能问析', backdrop: 'AGENT', accent: '#ff5a36' },
  { id: 'evaluation', module: '问析评测', code: 'MODULE 08 / ANALYSIS EVALUATION', title: '把 Agent 质量', highlight: '变成硬指标', description: '用固定验证案例与真实运行记录衡量 RAG 召回、SQL 一次通过、证据链完整度和端到端延迟。', action: '打开质量评测台', backdrop: 'EVAL', accent: '#2457ff' },
  { id: 'settings', module: '模型配置', code: 'MODULE 09 / MODEL CONNECTION', title: '把模型连接', highlight: '安全留在本机', description: '在浏览器中选择 DeepSeek 模型并验证 API Key；密钥仅保存在后端进程内存，重启即清除。', action: '打开模型配置', backdrop: 'MODEL', accent: '#087ea4' },
]
const overviewSlideIndex = ref(0)
const overviewCarouselPaused = ref(false)
const activeOverviewSlide = computed(() => overviewSlides[overviewSlideIndex.value])
let overviewTimer: number | undefined

function stopOverviewCarousel() {
  if (overviewTimer !== undefined) window.clearInterval(overviewTimer)
  overviewTimer = undefined
}
function startOverviewCarousel() {
  stopOverviewCarousel()
  if (overviewCarouselPaused.value) return
  overviewTimer = window.setInterval(() => {
    overviewSlideIndex.value = (overviewSlideIndex.value + 1) % overviewSlides.length
  }, 6500)
}
function selectOverviewSlide(index: number) {
  overviewSlideIndex.value = index
  startOverviewCarousel()
}
function pauseOverviewCarousel() {
  overviewCarouselPaused.value = true
  stopOverviewCarousel()
}
function resumeOverviewCarousel() {
  overviewCarouselPaused.value = false
  startOverviewCarousel()
}
function handleOverviewFocusOut(event: FocusEvent) {
  const carousel = event.currentTarget as HTMLElement
  if (!carousel.contains(event.relatedTarget as Node | null)) resumeOverviewCarousel()
}
const deepseekSourceLabel = computed(() => deepseekConfig.value?.source === 'runtime' ? '前端运行时配置' : '尚未配置')
const agentExamples = [
  { scene: '质量分析', code: 'QUALITY', question: '分析本月各工序良率，找出良率最低的工序' },
  { scene: '设备停机', code: 'EQUIPMENT', question: '本月各设备非计划停机时长排名' },
  { scene: '生产达成', code: 'PRODUCTION', question: '本月各产线计划达成率' },
]
const metricForm = reactive<Metric>({ metric_code: '', topic_code: 'quality', metric_name: '', description: '', formula: '', unit: '%', grain: '日期×产线', dimensions: [], mapped_tables: [], owner_name: '比赛项目组', version: '1.0', status: 'draft' })

const databaseReady = computed(() => ready.value?.status === 'ready')
const systemReady = computed(() => databaseReady.value && deepseekConfig.value?.configured === true)
const systemStatusLabel = computed(() => loading.value ? 'CONNECTING' : !databaseReady.value ? 'SERVICE OFFLINE' : systemReady.value ? 'SYSTEM READY' : 'MODEL REQUIRED')
const domains = computed(() => ['全部', ...new Set(tables.value.map((item) => item.business_domain))])
const visibleTables = computed(() => selectedDomain.value === '全部' ? tables.value : tables.value.filter((item) => item.business_domain === selectedDomain.value))
const visibleMetrics = computed(() => selectedTopic.value === 'all' ? metrics.value : metrics.value.filter((item) => item.topic_code === selectedTopic.value))
const graphTables = computed(() => tables.value.filter((table) => relations.value.some((relation) => relation.source_table === table.table_name || relation.target_table === table.table_name)))
const graphHeight = computed(() => {
  const factCount = graphTables.value.filter((table) => table.table_name.startsWith('fact_')).length
  const dimensionCount = graphTables.value.filter((table) => table.table_name.startsWith('dim_')).length
  return Math.max(470, Math.max(factCount, dimensionCount) * 74 + 90)
})

function graphPosition(tableName: string) {
  const isDimension = tableName.startsWith('dim_')
  const group = graphTables.value.filter((table) => table.table_name.startsWith(isDimension ? 'dim_' : 'fact_'))
  const index = Math.max(0, group.findIndex((item) => item.table_name === tableName))
  return { x: isDimension ? 540 : 42, y: 32 + index * 74 }
}
function formatNumber(value = 0) { return new Intl.NumberFormat('zh-CN').format(value) }
function formatDate(value?: string) { return value ? new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—' }
function formatDuration(value = 0) { return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms` }
const chartValues = computed(() => agentResult.value?.chart.series[0]?.data ?? [])
const chartBaseline = computed(() => {
  const values = chartValues.value
  if (!values.length) return 0
  const minimum = Math.min(...values)
  return agentResult.value?.chart.unit === '%' && minimum > 80 ? Math.floor(minimum - 2) : 0
})
const chartCeiling = computed(() => Math.max(...chartValues.value, chartBaseline.value + 1))
function chartHeight(value: number) { return `${Math.max(8, Math.min(100, 100 * (value - chartBaseline.value) / (chartCeiling.value - chartBaseline.value)))}%` }
function lineX(index: number) { return chartValues.value.length <= 1 ? 400 : 55 + index * 690 / (chartValues.value.length - 1) }
function lineY(value: number) { return 235 - 190 * (value - chartBaseline.value) / (chartCeiling.value - chartBaseline.value) }
const linePoints = computed(() => chartValues.value.map((value, index) => `${lineX(index)},${lineY(value)}`).join(' '))
const paretoLinePoints = computed(() => (agentResult.value?.chart.series[1]?.data ?? []).map((value, index, values) => `${values.length <= 1 ? 400 : 70 + index * 660 / (values.length - 1)},${245 - 2 * value}`).join(' '))
const qualityTrendValues = computed(() => qualityBrief.value?.charts.trend.map((item) => item.yield_rate) ?? [])
const qualityTrendMin = computed(() => Math.floor(Math.min(...(qualityTrendValues.value.length ? qualityTrendValues.value : [0])) - 0.5))
const qualityTrendMax = computed(() => Math.ceil(Math.max(...(qualityTrendValues.value.length ? qualityTrendValues.value : [1])) + 0.5))
const qualityTrendPoints = computed(() => qualityTrendValues.value.map((value, index, values) => `${values.length <= 1 ? 400 : 45 + index * 710 / (values.length - 1)},${220 - 165 * (value - qualityTrendMin.value) / Math.max(qualityTrendMax.value - qualityTrendMin.value, 1)}`).join(' '))
const qualityParetoMax = computed(() => Math.max(...(qualityBrief.value?.charts.pareto.map((item) => item.defect_count) ?? [1])))
const equipmentTimelinePoints = computed(() => (equipmentDiagnosis.value?.timeline ?? []).map((item, index, rows) => `${rows.length <= 1 ? 400 : 45 + index * 710 / (rows.length - 1)},${220 - 1.65 * item.anomaly_score}`).join(' '))
const equipmentDeviationMax = computed(() => Math.max(...(equipmentDiagnosis.value?.deviations.map((item) => Math.abs(item.robust_deviation)) ?? [1])))
const equipmentReasonMax = computed(() => Math.max(...(equipmentDiagnosis.value?.reason_distribution.map((item) => item.duration_minutes) ?? [1])))
const productionTrendPoints = computed(() => {
  const values = productionTrend.value?.daily_trend.map((item) => item.final_output) ?? []
  if (!values.length) return ''
  const minimum = Math.floor(Math.min(...values) - 30); const maximum = Math.ceil(Math.max(...values) + 30)
  return values.map((value, index) => `${values.length <= 1 ? 400 : 45 + index * 710 / (values.length - 1)},${220 - 165 * (value - minimum) / Math.max(maximum - minimum, 1)}`).join(' ')
})
const productionTrendMin = computed(() => Math.floor(Math.min(...(productionTrend.value?.daily_trend.map((item) => item.final_output) ?? [0])) - 30))
const productionTrendMax = computed(() => Math.ceil(Math.max(...(productionTrend.value?.daily_trend.map((item) => item.final_output) ?? [1])) + 30))
const productionTrendMid = computed(() => Math.round((productionTrendMax.value + productionTrendMin.value) / 2))
const productionSlopeMax = computed(() => Math.max(...(productionTrend.value?.ranking.map((item) => Math.abs(item.slope_per_day)) ?? [1])))
const algorithmMetric = (metrics: Record<string, number>) => Object.entries(metrics).map(([key, value]) => `${key} ${value}`).join(' · ')
function productionPointX(index: number) { const count = productionTrend.value?.daily_trend.length ?? 1; return count <= 1 ? 400 : 45 + index * 710 / (count - 1) }
function productionPointY(value: number) { return 220 - 165 * (value - productionTrendMin.value) / Math.max(productionTrendMax.value - productionTrendMin.value, 1) }
function equipmentPointX(index: number) { const count = equipmentDiagnosis.value?.timeline.length ?? 1; return count <= 1 ? 400 : 45 + index * 710 / (count - 1) }
function equipmentPointY(score: number) { return 220 - 1.65 * score }
function columnLabel(column: string) { return ({ process_name: '工序', product_name: '产品', equipment_name: '设备', event_reason: '原因', line_name: '产线', business_date: '日期', business_month: '月份', defect_type: '缺陷类型', yield_rate: '良率', defect_rate: '不良率', defect_count: '缺陷数量', cumulative_share: '累计占比', alarm_count: '报警次数', downtime_count: '停机次数', downtime_minutes: '停机时长', final_output: '完工产量', plan_attainment: '计划达成率', inspected_qty: '检验数量' } as Record<string, string>)[column] || column }
function formatCell(value: string | number, column: string) { return typeof value === 'number' ? `${formatNumber(value)}${['yield_rate', 'defect_rate', 'plan_attainment', 'cumulative_share'].includes(column) ? '%' : ''}` : value }
function clarificationFieldLabel(field: string) { return ({ scene: '业务场景', metric: '分析指标', time_range: '时间范围', dimension: '分析维度', goal: '分析目标' } as Record<string, string>)[field] || field }
function evaluationValue(metric: EvaluationMetric) { return metric.unit === 'ms' ? formatDuration(metric.value) : `${metric.value.toFixed(1)}${metric.unit}` }
function evaluationThreshold(metric: EvaluationMetric) { return `${metric.direction === 'gte' ? '≥' : '≤'} ${metric.unit === 'ms' ? formatDuration(metric.threshold) : `${metric.threshold}${metric.unit}`}` }
function evaluationBar(metric: EvaluationMetric) {
  if (metric.direction === 'lte') return `${Math.min(100, 100 * metric.threshold / Math.max(metric.value, 1))}%`
  return `${Math.min(100, 100 * metric.value / Math.max(metric.threshold, 1))}%`
}
function safeFileName(value: string) { return value.replace(/[\\/:*?"<>|\s]+/g, '-').replace(/-+/g, '-').slice(0, 64) || 'analysis' }
function triggerDownload(href: string, fileName: string, revoke = false) {
  const anchor = document.createElement('a')
  anchor.href = href; anchor.download = fileName; document.body.appendChild(anchor); anchor.click(); anchor.remove()
  if (revoke) window.setTimeout(() => URL.revokeObjectURL(href), 0)
}
function csvCell(value: unknown) {
  let text = value === null || value === undefined ? '' : String(value)
  if (/^[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}
function exportAgentCsv() {
  if (!agentResult.value) return
  const { columns, rows } = agentResult.value.result
  const lines = [columns.map((column) => csvCell(columnLabel(column))).join(',')]
  lines.push(...rows.map((row) => columns.map((column) => csvCell(row[column])).join(',')))
  const blob = new Blob(["\ufeff", lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const fileName = `a07-${agentResult.value.run_id.slice(0, 8)}-${safeFileName(agentResult.value.chart.title)}.csv`
  triggerDownload(URL.createObjectURL(blob), fileName, true)
  exportMessage.value = `CSV 已导出 · ${rows.length} 行`
}
function exportAgentPng() {
  if (!agentResult.value) return
  const result = agentResult.value
  const chart = result.chart
  const values = chart.series[0]?.data ?? []
  if (!values.length) return
  const canvas = document.createElement('canvas')
  canvas.width = 1400; canvas.height = 820
  const context = canvas.getContext('2d')
  if (!context) return
  const ink = '#17213d'; const blue = '#2457ff'; const orange = '#ff5b24'; const acid = '#c9ff3f'; const muted = '#66708a'
  context.fillStyle = '#fffefa'; context.fillRect(0, 0, canvas.width, canvas.height)
  context.fillStyle = blue; context.fillRect(0, 0, 24, canvas.height)
  context.fillStyle = ink; context.font = '700 42px "Microsoft YaHei", sans-serif'; context.fillText(chart.title, 90, 78)
  context.fillStyle = muted; context.font = '20px Consolas, monospace'; context.fillText(`${result.time_range.start}  →  ${result.time_range.end}   ·   ${result.result.row_count} ROWS   ·   ${result.run_id.slice(0, 8)}`, 92, 116)
  const plot = { left: 150, top: 175, width: 1110, height: 480 }
  const minimum = chart.unit === '%' && Math.min(...values) > 80 ? Math.floor(Math.min(...values) - 2) : 0
  const maximum = Math.max(...values, minimum + 1)
  context.strokeStyle = 'rgba(23,33,61,.18)'; context.lineWidth = 1
  context.font = '18px Consolas, monospace'; context.textAlign = 'right'; context.textBaseline = 'middle'
  for (let index = 0; index <= 4; index += 1) {
    const y = plot.top + index * plot.height / 4
    const tick = maximum - index * (maximum - minimum) / 4
    context.beginPath(); context.moveTo(plot.left, y); context.lineTo(plot.left + plot.width, y); context.stroke()
    context.fillStyle = muted; context.fillText(`${tick.toFixed(1)}${chart.unit}`, plot.left - 18, y)
  }
  context.strokeStyle = ink; context.lineWidth = 3
  context.beginPath(); context.moveTo(plot.left, plot.top); context.lineTo(plot.left, plot.top + plot.height); context.lineTo(plot.left + plot.width, plot.top + plot.height); context.stroke()
  const xFor = (index: number) => plot.left + (values.length <= 1 ? plot.width / 2 : 38 + index * (plot.width - 76) / (values.length - 1))
  const yFor = (value: number) => plot.top + plot.height - (value - minimum) * plot.height / Math.max(maximum - minimum, 1)
  if (chart.type === 'bar' || chart.type === 'pareto') {
    const slot = plot.width / values.length; const barWidth = Math.min(110, slot * .58)
    values.forEach((value, index) => {
      const height = (value - minimum) * plot.height / Math.max(maximum - minimum, 1)
      const x = plot.left + index * slot + (slot - barWidth) / 2
      context.fillStyle = index < 2 && chart.type === 'pareto' ? orange : blue
      context.fillRect(x, plot.top + plot.height - height, barWidth, height)
      context.fillStyle = ink; context.font = '700 18px Consolas, monospace'; context.textAlign = 'center'; context.fillText(String(value), x + barWidth / 2, plot.top + plot.height - height - 18)
    })
  } else {
    context.strokeStyle = blue; context.lineWidth = 6; context.lineJoin = 'round'; context.lineCap = 'round'; context.beginPath()
    values.forEach((value, index) => index ? context.lineTo(xFor(index), yFor(value)) : context.moveTo(xFor(index), yFor(value)))
    context.stroke(); values.forEach((value, index) => { context.fillStyle = orange; context.beginPath(); context.arc(xFor(index), yFor(value), 6, 0, Math.PI * 2); context.fill() })
  }
  if (chart.type === 'pareto' && chart.series[1]?.data.length) {
    const cumulative = chart.series[1].data
    const rightY = (value: number) => plot.top + plot.height - value * plot.height / 100
    context.strokeStyle = acid; context.lineWidth = 7; context.beginPath()
    cumulative.forEach((value, index) => index ? context.lineTo(xFor(index), rightY(value)) : context.moveTo(xFor(index), rightY(value)))
    context.stroke(); context.fillStyle = ink; context.textAlign = 'left'; context.font = '18px "Microsoft YaHei", sans-serif'; context.fillText('右轴：累计占比 0—100%', plot.left + plot.width - 230, plot.top - 26)
  }
  context.fillStyle = ink; context.font = '18px "Microsoft YaHei", sans-serif'; context.textAlign = 'center'; context.textBaseline = 'top'
  const labelStep = Math.max(1, Math.ceil(chart.categories.length / 10))
  chart.categories.forEach((category, index) => {
    if (index % labelStep !== 0 && index !== chart.categories.length - 1) return
    const x = chart.type === 'bar' || chart.type === 'pareto' ? plot.left + (index + .5) * plot.width / chart.categories.length : xFor(index)
    context.save(); context.translate(x, plot.top + plot.height + 18); context.rotate(-Math.PI / 8); context.fillText(String(category).slice(0, 14), 0, 0); context.restore()
  })
  context.save(); context.translate(48, plot.top + plot.height / 2); context.rotate(-Math.PI / 2); context.fillStyle = ink; context.font = '700 21px "Microsoft YaHei", sans-serif'; context.fillText(`${columnLabel(chart.y_field)}${chart.unit ? `（${chart.unit}）` : ''}`, 0, 0); context.restore()
  context.fillStyle = ink; context.font = '700 21px "Microsoft YaHei", sans-serif'; context.textAlign = 'center'; context.fillText(columnLabel(chart.x_field), plot.left + plot.width / 2, 765)
  const fileName = `a07-${result.run_id.slice(0, 8)}-${safeFileName(chart.title)}.png`
  triggerDownload(canvas.toDataURL('image/png'), fileName)
  exportMessage.value = `PNG 已导出 · 1400 × 820`
}
type FetchOptions = RequestInit & { timeoutMs?: number }
async function fetchJson<T>(url: string, options: FetchOptions = {}): Promise<T> {
  const { timeoutMs = 20_000, ...requestOptions } = options
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { ...requestOptions, signal: controller.signal })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as { detail?: string | { message?: string } }
      const detail = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message
      if (response.status === 504) throw new Error('模型请求超时，请稍后重试或切换 V4 Flash')
      throw new Error(detail || `请求失败：${response.status}`)
    }
    return response.status === 204 ? (undefined as T) : await response.json() as T
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw new Error('请求等待超时，请检查网络后重试')
    if (cause instanceof TypeError) throw new Error(navigator.onLine ? '无法连接后端服务，请确认 Docker 服务正常运行' : '网络连接已断开，请恢复网络后重试')
    throw cause
  } finally {
    window.clearTimeout(timer)
  }
}

function requireDeepseek(setError: (message: string) => void) {
  if (deepseekConfig.value?.configured) return true
  setError('DeepSeek 尚未配置，请先进入“模型配置”填写 API Key 并完成连接验证。')
  return false
}
function needsDeepseekConfig(message: string) { return message.startsWith('DeepSeek 尚未配置') || message.startsWith('DeepSeek Secret 未配置') }

async function loadWorkspace() {
  loading.value = true; error.value = ''
  try {
    const [r, b, config, s, t, rel, knowledge, m] = await Promise.all([
      fetchJson<ReadyPayload>('/api/ready'), fetchJson<BootstrapPayload>('/api/v1/system/bootstrap'),
      fetchJson<DeepSeekConfigStatus>('/api/v1/system/deepseek/config'),
      fetchJson<CatalogSummary>('/api/v1/catalog/summary'), fetchJson<CatalogTable[]>('/api/v1/catalog/tables'),
      fetchJson<Relation[]>('/api/v1/catalog/relations'), fetchJson<{ topics: Topic[]; rules: Rule[]; synonyms: Synonym[] }>('/api/v1/knowledge/overview'),
      fetchJson<Metric[]>('/api/v1/knowledge/metrics'),
    ])
    ready.value = r; bootstrap.value = b; deepseekConfig.value = config; deepseekSelectedModel.value = config.model; summary.value = s; tables.value = t; relations.value = rel
    topics.value = knowledge.topics; rules.value = knowledge.rules; synonyms.value = knowledge.synonyms; metrics.value = m
    if (!tableDetail.value && t.length) await selectTable(t[0].id)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '无法读取数据底座' }
  finally { loading.value = false }
}
async function refreshCatalog() {
  refreshing.value = true
  try { await fetchJson('/api/v1/catalog/refresh', { method: 'POST', timeoutMs: 120_000 }); tableDetail.value = null; await loadWorkspace() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '目录刷新失败' }
  finally { refreshing.value = false }
}
async function selectTable(tableId: number) { tableDetail.value = await fetchJson<TableDetail>(`/api/v1/catalog/tables/${tableId}`) }
function newMetric() {
  Object.assign(metricForm, { metric_code: '', topic_code: 'quality', metric_name: '', description: '', formula: '', unit: '%', grain: '日期×产线', dimensions: [], mapped_tables: [], owner_name: '比赛项目组', version: '1.0', status: 'draft' })
  dimensionText.value = ''; mappedTableText.value = ''; editingMetric.value = false; metricError.value = ''; metricEditorOpen.value = true
}
async function loadEvaluation() {
  if (evaluationLoading.value) return
  evaluationLoading.value = true; evaluationError.value = ''
  try { evaluation.value = await fetchJson<EvaluationOverview>('/api/v1/agent/evaluation/overview', { timeoutMs: 120_000 }) }
  catch (cause) { evaluationError.value = cause instanceof Error ? cause.message : '问析评测数据加载失败' }
  finally { evaluationLoading.value = false }
}
function openEvaluation() { activeView.value = 'evaluation'; void loadEvaluation() }
function openOverviewSlide() {
  if (activeOverviewSlide.value.id === 'evaluation') openEvaluation()
  else activeView.value = activeOverviewSlide.value.id
}
function editMetric(metric: Metric) {
  Object.assign(metricForm, metric); dimensionText.value = metric.dimensions.join('、'); mappedTableText.value = metric.mapped_tables.join('、')
  editingMetric.value = true; metricError.value = ''; metricEditorOpen.value = true
}
async function saveMetric() {
  if (metricSaving.value) return
  metricForm.dimensions = dimensionText.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean)
  metricForm.mapped_tables = mappedTableText.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean)
  const path = editingMetric.value ? `/api/v1/knowledge/metrics/${metricForm.metric_code}` : '/api/v1/knowledge/metrics'
  metricSaving.value = true; metricError.value = ''
  try {
    await fetchJson(path, { method: editingMetric.value ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(metricForm), timeoutMs: 60_000 })
    metricEditorOpen.value = false; metrics.value = await fetchJson<Metric[]>('/api/v1/knowledge/metrics')
  } catch (cause) { metricError.value = cause instanceof Error ? cause.message : '指标口径保存失败' }
  finally { metricSaving.value = false }
}
async function runAgent() {
  if (agentRunning.value || !agentQuestion.value.trim()) return
  agentRunning.value = true; agentError.value = ''; agentResult.value = null; agentClarification.value = null; exportMessage.value = ''
  try {
    const response = await fetchJson<AgentRun | AgentClarification>('/api/v1/agent/runs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: agentQuestion.value.trim(), clarification_id: pendingClarificationId.value }), timeoutMs: 175_000,
    })
    if (response.status === 'needs_clarification') {
      agentClarification.value = response; pendingClarificationId.value = response.clarification_id
    } else {
      agentResult.value = response; pendingClarificationId.value = null
    }
  } catch (cause) { agentError.value = cause instanceof Error ? cause.message : 'Agent 执行失败' }
  finally { agentRunning.value = false }
}
function continueWithClarification(question: string) { agentQuestion.value = question; void runAgent() }
function chooseAgentQuestion(question: string) {
  agentQuestion.value = question; agentClarification.value = null; pendingClarificationId.value = null; agentError.value = ''
}
async function generateQualityBrief() {
  if (qualityBriefRunning.value) return
  if (!requireDeepseek((message) => { qualityBriefError.value = message })) return
  qualityBriefRunning.value = true; qualityBriefError.value = ''
  try { qualityBrief.value = await fetchJson<QualityBrief>('/api/v1/agent/quality/brief', { method: 'POST', timeoutMs: 175_000 }) }
  catch (cause) { qualityBriefError.value = cause instanceof Error ? cause.message : '质量简报生成失败' }
  finally { qualityBriefRunning.value = false }
}
function openQualityQuestion(question: string) {
  chooseAgentQuestion(question); agentResult.value = null; activeView.value = 'agent'
}
async function generateEquipmentDiagnosis() {
  if (equipmentRunning.value) return
  if (!requireDeepseek((message) => { equipmentError.value = message })) return
  equipmentRunning.value = true; equipmentError.value = ''
  try { equipmentDiagnosis.value = await fetchJson<EquipmentDiagnosis>('/api/v1/agent/equipment/diagnosis', { method: 'POST', timeoutMs: 175_000 }) }
  catch (cause) { equipmentError.value = cause instanceof Error ? cause.message : '设备异常诊断失败' }
  finally { equipmentRunning.value = false }
}
function openEquipmentQuestion(question: string) {
  chooseAgentQuestion(question); agentResult.value = null; activeView.value = 'agent'
}
async function generateProductionTrend() {
  if (productionRunning.value) return
  if (!requireDeepseek((message) => { productionError.value = message })) return
  productionRunning.value = true; productionError.value = ''
  try { productionTrend.value = await fetchJson<ProductionTrend>('/api/v1/agent/production/trend', { method: 'POST', timeoutMs: 175_000 }) }
  catch (cause) { productionError.value = cause instanceof Error ? cause.message : '生产趋势分析失败' }
  finally { productionRunning.value = false }
}
async function evaluateAlgorithms() {
  if (algorithmRunning.value) return
  algorithmRunning.value = true; algorithmError.value = ''
  try { algorithmSuite.value = await fetchJson<AlgorithmSuite>('/api/v1/agent/algorithms/evaluate', { method: 'POST', timeoutMs: 120_000 }) }
  catch (cause) { algorithmError.value = cause instanceof Error ? cause.message : '六算法验收失败' }
  finally { algorithmRunning.value = false }
}
async function saveDeepseekConfig() {
  const apiKey = deepseekApiKey.value.trim()
  deepseekConfigError.value = ''; deepseekConfigMessage.value = ''
  if (!deepseekConfig.value?.configured && apiKey.length < 12) { deepseekConfigError.value = '请输入完整的 DeepSeek API Key'; return }
  if (apiKey && apiKey.length < 12) { deepseekConfigError.value = '请输入完整的 DeepSeek API Key，或留空沿用当前 Key'; return }
  deepseekConfigSaving.value = true
  try {
    deepseekConfig.value = await fetchJson<DeepSeekConfigStatus>('/api/v1/system/deepseek/config', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: apiKey || null, model: deepseekSelectedModel.value, verify: true }), timeoutMs: 165_000,
    })
    deepseekApiKey.value = ''; showDeepseekApiKey.value = false
    if (ready.value) ready.value.dependencies.deepseek = 'configured'
    deepseekConfigMessage.value = `连接验证通过，当前 Agent 已切换至 ${deepseekConfig.value.model}。`
  } catch (cause) { deepseekConfigError.value = cause instanceof Error ? cause.message : 'DeepSeek 配置失败' }
  finally { deepseekConfigSaving.value = false }
}
async function clearDeepseekConfig() {
  if (!deepseekConfig.value?.can_clear || deepseekConfigSaving.value) return
  deepseekConfigSaving.value = true; deepseekConfigError.value = ''; deepseekConfigMessage.value = ''
  try {
    deepseekConfig.value = await fetchJson<DeepSeekConfigStatus>('/api/v1/system/deepseek/config', { method: 'DELETE' })
    deepseekSelectedModel.value = deepseekConfig.value.model
    if (ready.value) ready.value.dependencies.deepseek = deepseekConfig.value.configured ? 'configured' : 'not_configured'
    deepseekConfigMessage.value = '页面临时 Key 已安全清除。'
  } catch (cause) { deepseekConfigError.value = cause instanceof Error ? cause.message : '清除配置失败' }
  finally { deepseekConfigSaving.value = false }
}
function openProductionQuestion(question: string) {
  chooseAgentQuestion(question); agentResult.value = null; activeView.value = 'agent'
}
onMounted(() => {
  loadWorkspace()
  startOverviewCarousel()
})
onBeforeUnmount(stopOverviewCarousel)
</script>

<template>
  <aside class="desktop-only-gate" role="status" aria-label="桌面端访问提示">
    <div class="desktop-gate-mark">A<span>07</span></div>
    <p class="section-code">DESKTOP WORKSPACE ONLY</p>
    <h2>请使用电脑浏览器<br />打开分析工作台</h2>
    <p>比赛版本已聚焦桌面端数据分析体验，不再提供手机端业务页面。</p>
    <code>RECOMMENDED DESKTOP · 1440 × 900</code>
  </aside>
  <main class="shell">
    <div class="blueprint" aria-hidden="true"></div>
    <header class="masthead">
      <div class="brand-lockup"><div class="mark">A<span>07</span></div><div><p class="eyebrow">MANUFACTURING INTELLIGENCE / CONTEST BUILD</p><h1>企业数据底座 <em>智能问析 Agent</em></h1></div></div>
      <div class="phase-stamp"><span>BUILD PHASE</span><strong>{{ bootstrap?.phase ?? '—' }}</strong></div>
    </header>
    <nav class="view-nav" aria-label="主功能导航">
      <button :class="{ active: activeView === 'overview' }" @click="activeView = 'overview'">总览 <span>01</span></button>
      <button :class="{ active: activeView === 'catalog' }" @click="activeView = 'catalog'">数据目录 <span>02</span></button>
      <button :class="{ active: activeView === 'knowledge' }" @click="activeView = 'knowledge'">业务知识 <span>03</span></button>
      <button :class="{ active: activeView === 'quality' }" @click="activeView = 'quality'">质量驾驶舱 <span>04</span></button>
      <button :class="{ active: activeView === 'equipment' }" @click="activeView = 'equipment'">设备诊断 <span>05</span></button>
      <button :class="{ active: activeView === 'production' }" @click="activeView = 'production'">生产趋势 <span>06</span></button>
      <button :class="{ active: activeView === 'agent' }" @click="activeView = 'agent'">智能问析 <span>07</span></button>
      <button :class="{ active: activeView === 'evaluation' }" @click="openEvaluation">问析评测 <span>08</span></button>
      <button :class="{ active: activeView === 'settings' }" @click="activeView = 'settings'">模型配置 <span>09</span></button>
      <div class="system-pill" :class="{ ready: systemReady }"><i></i>{{ systemStatusLabel }}</div>
    </nav>
    <div v-if="error" class="error-banner">{{ error }} <button @click="loadWorkspace">重试</button></div>
    <div v-if="loading" class="loading-screen"><i></i><span>正在扫描制造数据资产…</span></div>

    <template v-else>
      <section v-if="activeView === 'overview'" class="overview-view">
        <div class="hero-grid overview-carousel" :class="{ paused: overviewCarouselPaused }" role="region" aria-roledescription="carousel" aria-label="系统功能模块轮播" @mouseenter="pauseOverviewCarousel" @mouseleave="resumeOverviewCarousel" @focusin="pauseOverviewCarousel" @focusout="handleOverviewFocusOut">
          <Transition name="overview-slide" mode="out-in">
            <article :key="activeOverviewSlide.id" class="hero-copy overview-slide" :style="{ '--slide-accent': activeOverviewSlide.accent }" :data-backdrop="activeOverviewSlide.backdrop">
              <p class="section-code">{{ activeOverviewSlide.code }}</p>
              <h2>{{ activeOverviewSlide.title }}<br /><span>{{ activeOverviewSlide.highlight }}</span></h2>
              <p>{{ activeOverviewSlide.description }}</p>
              <button class="primary-action" @click="openOverviewSlide">{{ activeOverviewSlide.action }} <b>→</b></button>
              <div class="overview-slide-progress" aria-hidden="true"><i :key="overviewSlideIndex"></i></div>
            </article>
          </Transition>
          <aside class="overview-module-rail">
            <header><span>MODULE LOOP</span><strong>{{ String(overviewSlideIndex + 1).padStart(2, '0') }} / {{ String(overviewSlides.length).padStart(2, '0') }}</strong></header>
            <div>
              <button v-for="(slide, index) in overviewSlides" :key="slide.id" :class="{ active: index === overviewSlideIndex }" :aria-current="index === overviewSlideIndex ? 'true' : undefined" @click="selectOverviewSlide(index)"><b>{{ String(index + 2).padStart(2, '0') }}</b><span>{{ slide.module }}</span><i></i></button>
            </div>
            <footer><span>DATASET ANCHOR</span><strong>{{ summary?.dataset_max_business_date }}</strong></footer>
          </aside>
        </div>
        <div class="stat-strip">
          <div><small>TABLES</small><strong>{{ summary?.table_count }}</strong><span>9 主表 + 1 留出表</span></div><div><small>COLUMNS</small><strong>{{ summary?.column_count }}</strong><span>含注释与脱敏样例</span></div>
          <div><small>RELATIONS</small><strong>{{ summary?.relation_count }}</strong><span>真实外键关系</span></div><div><small>ROWS</small><strong>{{ formatNumber(summary?.total_rows) }}</strong><span>可解释演示记录</span></div>
        </div>
        <div class="topic-grid">
          <article v-for="(topic, index) in topics" :key="topic.topic_code" :style="{ '--topic': topic.accent_color }"><div class="topic-number">0{{ index + 1 }}</div><span>{{ topic.topic_code.toUpperCase() }}</span><h3>{{ topic.topic_name }}</h3><p>{{ topic.description }}</p><footer><b>{{ topic.metric_count }}</b> 指标 · <b>{{ topic.rule_count }}</b> 强规则 · <b>{{ topic.object_count }}</b> 对象</footer></article>
        </div>
        <section class="next-band"><span>NEXT / PHASE 04</span><h3>{{ bootstrap?.next_milestone }}</h3><p>混合 RAG → DeepSeek 规划 → Text-to-SQL → 安全执行/修复 → 动态图表 → 有据结论</p><div><i></i></div></section>
      </section>

      <section v-if="activeView === 'catalog'" class="catalog-view">
        <header class="section-header"><div><p class="section-code">LIVE POSTGRESQL CATALOG</p><h2>数据资源目录</h2></div><div class="header-actions"><span>最近扫描 {{ formatDate(summary?.refreshed_at) }}</span><button @click="refreshCatalog" :disabled="refreshing">{{ refreshing ? '扫描中…' : '刷新元数据' }}</button></div></header>
        <div class="filter-row"><button v-for="domain in domains" :key="domain" :class="{ active: selectedDomain === domain }" @click="selectedDomain = domain">{{ domain }}</button></div>
        <div class="catalog-layout">
          <aside class="table-list"><button v-for="table in visibleTables" :key="table.id" :class="{ active: tableDetail?.id === table.id }" @click="selectTable(table.id)"><span>{{ table.business_domain }}</span><strong>{{ table.display_name }}</strong><code>{{ table.schema_name }}.{{ table.table_name }}</code><small>{{ table.column_count }} 字段 · {{ formatNumber(table.row_count) }} 行</small></button></aside>
          <article v-if="tableDetail" class="table-inspector">
            <header><div><span>TABLE / {{ tableDetail.business_domain }}</span><h3>{{ tableDetail.display_name }}</h3><code>{{ tableDetail.schema_name }}.{{ tableDetail.table_name }}</code></div><b>{{ formatNumber(tableDetail.row_count) }}<small>ROWS</small></b></header>
            <p class="table-description">{{ tableDetail.description }}</p>
            <div class="column-table"><div class="column-head"><span>字段 / 类型</span><span>业务说明</span><span>样例值</span></div><div v-for="column in tableDetail.columns" :key="column.id" class="column-row"><span><code>{{ column.column_name }}</code><small>{{ column.data_type }} <i v-if="column.is_primary_key">PK</i></small></span><span>{{ column.description || '—' }}</span><span class="samples"><kbd v-for="sample in column.sample_values" :key="String(sample)">{{ sample }}</kbd></span></div></div>
          </article>
        </div>
        <section class="relation-section"><div class="relation-copy"><p class="section-code">VERIFIED JOIN PATHS</p><h3>真实关系图</h3><p>仅展示数据库外键，不允许模型猜测连接键。事实表沿多对一关系连接到维表和上游事实。</p><strong>{{ relations.length }}<small> VERIFIED EDGES</small></strong></div><div class="relation-canvas"><svg :viewBox="`0 0 760 ${graphHeight}`" role="img" aria-label="数据表关系图"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs><line v-for="relation in relations" :key="relation.id" :x1="graphPosition(relation.source_table).x + 176" :y1="graphPosition(relation.source_table).y + 22" :x2="graphPosition(relation.target_table).x" :y2="graphPosition(relation.target_table).y + 22" marker-end="url(#arrow)" /><g v-for="table in graphTables" :key="table.id" :transform="`translate(${graphPosition(table.table_name).x} ${graphPosition(table.table_name).y})`"><rect width="176" height="44" rx="2" /><text x="12" y="18">{{ table.display_name }}</text><text class="code" x="12" y="34">{{ table.table_name }}</text></g></svg></div></section>
      </section>

      <section v-if="activeView === 'knowledge'" class="knowledge-view">
        <header class="section-header"><div><p class="section-code">BUSINESS SEMANTIC LAYER</p><h2>业务知识管理</h2></div><button class="primary-action compact" @click="newMetric">新增指标 <b>＋</b></button></header>
        <div class="topic-tabs"><button :class="{ active: selectedTopic === 'all' }" @click="selectedTopic = 'all'">全部</button><button v-for="topic in topics" :key="topic.topic_code" :class="{ active: selectedTopic === topic.topic_code }" @click="selectedTopic = topic.topic_code">{{ topic.topic_name }}</button></div>
        <div class="knowledge-layout"><div class="metric-list"><article v-for="metric in visibleMetrics" :key="metric.metric_code" @click="editMetric(metric)"><header><span>{{ topics.find((item) => item.topic_code === metric.topic_code)?.topic_name }}</span><i :class="metric.status">{{ metric.status }}</i></header><h3>{{ metric.metric_name }} <small>{{ metric.unit }}</small></h3><p>{{ metric.description }}</p><code>{{ metric.formula }}</code><footer><span>粒度：{{ metric.grain }}</span><span>v{{ metric.version }} · {{ metric.owner_name }}</span></footer></article></div><aside class="rule-stack"><div><p class="section-code">NON-NEGOTIABLE</p><h3>Agent 强规则</h3></div><article v-for="rule in rules" :key="rule.rule_code"><span>{{ rule.topic_code }}</span><strong>{{ rule.rule_name }}</strong><p>{{ rule.rule_content }}</p></article><div class="synonym-cloud"><p class="section-code">SYNONYMS</p><span v-for="item in synonyms" :key="`${item.canonical_term}-${item.synonym_term}`">{{ item.synonym_term }} → {{ item.canonical_term }}</span></div></aside></div>
      </section>

      <section v-if="activeView === 'quality'" class="quality-view">
        <header class="quality-hero">
          <div class="quality-hero-copy">
            <p class="section-code">PHASE 04 / QUALITY INTELLIGENCE ROOM</p>
            <h2>质量，不止一个<span>良率</span></h2>
            <p>LangGraph 将良率环比、工序短板、缺陷 Pareto 和每日趋势编排成同一份有据简报。所有数据截至 <b>2025-12-29</b>，不把相关性包装成根因。</p>
            <div class="quality-actions">
              <button class="quality-generate" :disabled="qualityBriefRunning" @click="generateQualityBrief">
                <span v-if="qualityBriefRunning" class="button-spinner"></span>
                {{ qualityBriefRunning ? '正在编排质量简报' : qualityBrief ? '重新生成质量简报' : '生成本月质量简报' }} <b>↗</b>
              </button>
              <small>RAG × 3 · READ-ONLY SQL × 4 · DEEPSEEK BRIEF</small>
            </div>
          </div>
          <div class="quality-seal" aria-hidden="true"><small>QUALITY</small><strong>04</strong><span>DEC / 2025</span></div>
        </header>

        <div class="quality-question-strip">
          <span>下钻问析</span>
          <button @click="openQualityQuestion('本月缺陷类型 Pareto 分析')"><b>01</b> 缺陷 Pareto <i>→</i></button>
          <button @click="openQualityQuestion('最近30天每日良率趋势')"><b>02</b> 每日良率趋势 <i>→</i></button>
          <button @click="openQualityQuestion('对比本月与上月总体良率')"><b>03</b> 月度环比 <i>→</i></button>
        </div>

        <div v-if="qualityBriefError" class="agent-error"><strong>质量简报未完成</strong><p>{{ qualityBriefError }}</p><button v-if="needsDeepseekConfig(qualityBriefError)" @click="activeView = 'settings'">前往模型配置</button><button v-else @click="generateQualityBrief">重新生成</button></div>
        <div v-if="qualityBriefRunning" class="quality-loading">
          <div class="quality-loader"><i></i><i></i><i></i><i></i></div>
          <div><span>LANGGRAPH QUALITY BRIEF</span><h3>正在汇集质量证据与真实指标</h3><p>检索三组 EvidenceBundle，执行四组只读聚合，再由 DeepSeek 形成管理层简报。</p></div>
        </div>
        <section v-else-if="!qualityBrief" class="quality-empty">
          <div class="empty-figure"><span>Q</span><i></i></div>
          <div><p class="section-code">READY TO COMPOSE</p><h3>一键生成可演示的质量分析闭环</h3><p>不是静态仪表盘。点击后现场运行 LangGraph、RAG、PostgreSQL 与 DeepSeek，并展示完整轨迹。</p></div>
        </section>

        <template v-if="qualityBrief && !qualityBriefRunning">
          <section class="quality-kpis">
            <article class="kpi-primary"><span>本月总体良率</span><strong>{{ qualityBrief.assessment.current_yield }}<small>%</small></strong><p :class="qualityBrief.assessment.yield_delta_pp < 0 ? 'down' : 'up'">{{ qualityBrief.assessment.yield_delta_pp > 0 ? '+' : '' }}{{ qualityBrief.assessment.yield_delta_pp }} pp <i>环比</i></p></article>
            <article><span>检验数量</span><strong>{{ formatNumber(qualityBrief.assessment.inspected_qty) }}</strong><small>件 / 12.01—12.29</small></article>
            <article><span>最低良率工序</span><strong>{{ qualityBrief.assessment.worst_process.process_name }}</strong><small>{{ qualityBrief.assessment.worst_process.yield_rate }}% · {{ formatNumber(qualityBrief.assessment.worst_process.inspected_qty) }} 件检验</small></article>
            <article class="kpi-alert"><span>首要缺陷</span><strong>{{ qualityBrief.assessment.top_defect.defect_type }}</strong><small>占全部缺陷 {{ qualityBrief.assessment.top_defect.defect_share }}%</small></article>
          </section>

          <div class="quality-chart-grid">
            <section class="quality-panel pareto-panel">
              <header><div><p class="section-code">DEFECT PARETO / 80-20</p><h3>关键缺陷贡献</h3></div><span>{{ qualityBrief.assessment.vital_few.length }} VITAL FEW</span></header>
              <div class="quality-pareto" role="img" aria-label="缺陷 Pareto 图">
                <div v-for="item in qualityBrief.charts.pareto" :key="item.defect_type" class="pareto-item">
                  <div><span>{{ item.defect_type }}</span><b>{{ formatNumber(item.defect_count) }}</b></div>
                  <i><em :style="{ width: `${100 * item.defect_count / qualityParetoMax}%` }"></em></i>
                  <small>{{ item.defect_share }}% / 累计 {{ item.cumulative_share }}%</small>
                </div>
              </div>
              <footer>累计占比达到 80% 前：<b>{{ qualityBrief.assessment.vital_few.join('、') }}</b></footer>
            </section>

            <section class="quality-panel trend-panel">
              <header><div><p class="section-code">30-DAY YIELD SIGNAL</p><h3>每日良率走势</h3></div><span>30 POINTS</span></header>
              <div class="quality-trend">
                <div class="chart-y-title">良率（%）</div>
                <div class="chart-y-ticks"><span>{{ qualityTrendMax }}</span><span>{{ ((qualityTrendMax + qualityTrendMin) / 2).toFixed(1) }}</span><span>{{ qualityTrendMin }}</span></div>
                <svg viewBox="0 0 800 260" preserveAspectRatio="none" role="img" aria-label="最近30天每日良率趋势">
                  <line v-for="y in [55, 137, 220]" :key="y" x1="45" :y1="y" x2="755" :y2="y" />
                  <line class="axis-line" x1="45" y1="40" x2="45" y2="220" />
                  <line class="axis-line" x1="45" y1="220" x2="755" y2="220" />
                  <polyline :points="qualityTrendPoints" />
                  <circle v-if="qualityBrief.charts.trend.length" cx="755" :cy="qualityTrendPoints.split(' ').at(-1)?.split(',')[1]" r="7" />
                </svg>
                <div class="trend-axis"><span>{{ qualityBrief.charts.trend[0]?.business_date.slice(5) }}</span><span>{{ qualityBrief.charts.trend.at(-1)?.business_date.slice(5) }}</span></div>
                <div class="chart-x-title">业务日期（月-日）</div>
              </div>
              <div class="process-pulse"><span v-for="item in qualityBrief.charts.process" :key="item.process_name"><b>{{ item.yield_rate }}%</b>{{ item.process_name }}</span></div>
            </section>
          </div>

          <section class="quality-brief-card">
            <header><div><p class="section-code">DEEPSEEK MANAGEMENT BRIEF</p><h3>{{ qualityBrief.brief.headline }}</h3></div><span>{{ qualityBrief.brief.generation_mode.toUpperCase() }}</span></header>
            <p class="brief-summary">{{ qualityBrief.brief.summary }}</p>
            <div class="brief-columns">
              <div><span>风险观察</span><ol><li v-for="risk in qualityBrief.brief.risks" :key="risk">{{ risk }}</li></ol></div>
              <div><span>建议动作</span><ol><li v-for="action in qualityBrief.brief.actions" :key="action">{{ action }}</li></ol></div>
            </div>
            <footer><code>{{ qualityBrief.run_id }}</code><span>{{ formatDuration(qualityBrief.duration_ms) }} · 数据边界 {{ qualityBrief.period.start }}—{{ qualityBrief.period.end }}</span></footer>
          </section>

          <section class="quality-proof-grid">
            <div class="quality-proof"><p class="section-code">EVIDENCE PACKS</p><article v-for="item in qualityBrief.evidence" :key="item.metric_code"><b>{{ item.metric }}</b><code>{{ item.formula }}</code><span>{{ item.tables.join(' + ') }}</span></article></div>
            <div class="quality-proof"><p class="section-code">LANGGRAPH TRACE</p><article v-for="(step, index) in qualityBrief.trace" :key="step.node_name"><b>0{{ index + 1 }} · {{ step.display_name }}</b><span>{{ step.summary }}</span><small>{{ formatDuration(step.duration_ms) }}</small></article></div>
          </section>
        </template>
      </section>

      <section v-if="activeView === 'equipment'" class="equipment-view">
        <header class="equipment-hero">
          <div class="equipment-intro">
            <p class="section-code">PHASE 05 / MACHINE BEHAVIOR DOSSIER</p>
            <h2>别等停机，<br /><span>先看偏离</span></h2>
            <p>用 61 天历史设备日作为基线，对 29 天评分窗口进行无监督异常识别。算法说明“哪里不一样”，DeepSeek 帮助组织核查路径，但不替代根因分析。</p>
            <button class="equipment-run" :disabled="equipmentRunning" @click="generateEquipmentDiagnosis"><span v-if="equipmentRunning" class="button-spinner"></span>{{ equipmentRunning ? '正在执行异常 Recipe' : equipmentDiagnosis ? '重新运行设备诊断' : '运行设备异常诊断' }} <b>↗</b></button>
          </div>
          <div class="machine-poster" aria-hidden="true">
            <span>IF</span><svg viewBox="0 0 280 90"><polyline points="0,45 35,44 48,18 63,72 78,43 130,44 146,36 159,50 176,43 230,44 242,8 254,80 268,44 280,45" /></svg>
            <small>ISOLATION FOREST<br />DAILY FEATURE RECIPE</small>
          </div>
        </header>

        <div class="equipment-query-strip"><span>SQL 下钻</span><button @click="openEquipmentQuestion('本月各设备报警次数排名')"><b>01</b> 报警频次 <i>→</i></button><button @click="openEquipmentQuestion('本月各设备非计划停机次数排名')"><b>02</b> 停机次数 <i>→</i></button><button @click="openEquipmentQuestion('本月各设备非计划停机时长排名')"><b>03</b> 停机时长 <i>→</i></button></div>
        <div v-if="equipmentError" class="agent-error"><strong>设备诊断未完成</strong><p>{{ equipmentError }}</p><button v-if="needsDeepseekConfig(equipmentError)" @click="activeView = 'settings'">前往模型配置</button><button v-else @click="generateEquipmentDiagnosis">重新运行</button></div>
        <div v-if="equipmentRunning" class="equipment-loading"><div class="radar-loader"><i></i><b></b><span></span></div><div><p class="section-code">RECIPE IS RUNNING</p><h3>正在训练基线并扫描设备日偏离</h3><p>Feature SQL → StandardScaler → Isolation Forest → Median/IQR Explanation → DeepSeek Brief</p></div></div>
        <section v-else-if="!equipmentDiagnosis" class="equipment-empty"><div class="machine-index"><b>E08</b><span>KNOWN SIGNAL / HIDDEN FROM MODEL</span></div><div><p class="section-code">AUDITABLE ANOMALY WORKFLOW</p><h3>一次运行，展示从特征到解释的完整算法证据</h3><p>系统不会读取预设答案。E08 的异常模式埋在设备事件数据中，需由固定 Recipe 现场识别。</p></div></section>

        <template v-if="equipmentDiagnosis && !equipmentRunning">
          <section class="equipment-alert-band">
            <div class="alert-identity"><span>TOP ANOMALY</span><strong>{{ equipmentDiagnosis.assessment.top_equipment.equipment_id }}</strong><h3>{{ equipmentDiagnosis.assessment.top_equipment.equipment_name }}</h3><p>{{ equipmentDiagnosis.assessment.top_equipment.line_name }}</p></div>
            <div><span>异常日</span><strong>{{ equipmentDiagnosis.assessment.top_equipment.anomaly_days }}<small>/29</small></strong><p>{{ equipmentDiagnosis.assessment.anomaly_rate_pct }}% 评分窗口</p></div>
            <div><span>最大单次停机</span><strong>{{ equipmentDiagnosis.assessment.top_equipment.max_single_duration }}<small> min</small></strong><p>{{ equipmentDiagnosis.assessment.top_anomaly_date }}</p></div>
            <div><span>模型评分峰值</span><strong>{{ equipmentDiagnosis.assessment.top_anomaly_score }}</strong><p>0—100 相对尺度</p></div>
            <div class="model-ticket"><span>MODEL RECIPE</span><b>{{ equipmentDiagnosis.recipe.algorithm }}</b><code>v{{ equipmentDiagnosis.recipe.version }} · seed {{ equipmentDiagnosis.recipe.parameters.random_state }}</code></div>
          </section>

          <div class="equipment-main-grid">
            <section class="equipment-panel fleet-panel"><header><div><p class="section-code">FLEET ANOMALY RANK</p><h3>九台设备扫描</h3></div><span>29 DAYS</span></header><div class="fleet-list"><article v-for="(item, index) in equipmentDiagnosis.ranking" :key="item.equipment_id" :class="{ hot: index === 0 }"><b>{{ String(index + 1).padStart(2, '0') }}</b><div><strong>{{ item.equipment_name }}</strong><span>{{ item.equipment_id }} · {{ item.equipment_type }}</span></div><i><em :style="{ width: `${item.max_anomaly_score}%` }"></em></i><small>{{ item.anomaly_days }} 异常日</small></article></div></section>
            <section class="equipment-panel signal-panel"><header><div><p class="section-code">ANOMALY SIGNAL / TOP MACHINE</p><h3>{{ equipmentDiagnosis.assessment.top_equipment.equipment_name }} 时间信号</h3></div><span>IF SCORE</span></header><div class="signal-chart"><div class="chart-y-title">异常评分</div><div class="chart-y-ticks"><span>100</span><span>50</span><span>0</span></div><svg viewBox="0 0 800 260" preserveAspectRatio="none"><line v-for="y in [55, 137, 220]" :key="y" x1="45" :y1="y" x2="755" :y2="y" /><line class="axis-line" x1="45" y1="40" x2="45" y2="220" /><line class="axis-line" x1="45" y1="220" x2="755" y2="220" /><polyline :points="equipmentTimelinePoints" /><g v-for="(item, index) in equipmentDiagnosis.timeline" :key="item.business_date"><circle v-if="item.is_anomaly" :cx="equipmentPointX(index)" :cy="equipmentPointY(item.anomaly_score)" r="6" /></g></svg><div class="chart-date-axis"><span>{{ equipmentDiagnosis.timeline[0]?.business_date.slice(5) }}</span><b>异常阈值由训练基线确定</b><span>{{ equipmentDiagnosis.timeline.at(-1)?.business_date.slice(5) }}</span></div><div class="chart-x-title">业务日期（月-日）</div></div><footer><span>停机累计 <b>{{ formatNumber(equipmentDiagnosis.assessment.top_equipment.total_downtime_minutes) }} min</b></span><span>报警事件 <b>{{ equipmentDiagnosis.assessment.top_equipment.alarm_count }} 次</b></span></footer></section>
          </div>

          <section class="deviation-section"><header><div><p class="section-code">ROBUST DEVIATION EXPLANATION</p><h3>它为什么被判为异常</h3></div><p>当前最高异常日相对该设备历史中位数 / IQR，不代表因果根因。</p></header><div class="deviation-grid"><article v-for="(item, index) in equipmentDiagnosis.deviations" :key="item.feature"><span>0{{ index + 1 }} · {{ item.feature }}</span><h4>{{ item.label }}</h4><div><b>{{ item.current }}</b><i><em :style="{ width: `${100 * Math.abs(item.robust_deviation) / equipmentDeviationMax}%` }"></em></i><small>基线 {{ item.baseline_median }}</small></div><footer><strong>{{ item.robust_deviation > 0 ? '+' : '' }}{{ item.robust_deviation }} IQR</strong><span v-if="item.change_pct !== null">{{ item.change_pct > 0 ? '+' : '' }}{{ item.change_pct }}%</span><span v-else>基线为 0</span></footer></article></div></section>

          <div class="equipment-insight-grid">
            <section class="reason-card"><header><p class="section-code">EVENT REASON / REVIEW CLUES</p><h3>事件原因线索</h3></header><div><article v-for="item in equipmentDiagnosis.reason_distribution" :key="item.event_reason"><span>{{ item.event_reason }}</span><i><em :style="{ width: `${100 * item.duration_minutes / equipmentReasonMax}%` }"></em></i><b>{{ formatNumber(item.duration_minutes) }} min</b></article></div><footer>原因分布仅用于安排核查，不作为模型根因结论。</footer></section>
            <section class="equipment-brief"><header><p class="section-code">DEEPSEEK RELIABILITY BRIEF</p><span>{{ equipmentDiagnosis.brief.generation_mode.toUpperCase() }}</span></header><h3>{{ equipmentDiagnosis.brief.headline }}</h3><p>{{ equipmentDiagnosis.brief.summary }}</p><div><article><b>风险观察</b><ul><li v-for="risk in equipmentDiagnosis.brief.risks" :key="risk">{{ risk }}</li></ul></article><article><b>建议动作</b><ul><li v-for="action in equipmentDiagnosis.brief.actions" :key="action">{{ action }}</li></ul></article></div></section>
          </div>

          <section class="equipment-proof-grid"><article class="recipe-proof"><p class="section-code">RECIPE CONTRACT</p><h3>{{ equipmentDiagnosis.recipe.name }}</h3><div><span v-for="feature in equipmentDiagnosis.recipe.features" :key="feature">{{ feature }}</span></div><p>{{ equipmentDiagnosis.recipe.explanation_rule }}</p><details><summary>查看审核 Feature SQL</summary><pre>{{ equipmentDiagnosis.recipe.feature_sql }}</pre></details></article><article class="equipment-trace"><p class="section-code">LANGGRAPH / 5 NODES</p><div v-for="(step, index) in equipmentDiagnosis.trace" :key="step.node_name"><b>0{{ index + 1 }}</b><span><strong>{{ step.display_name }}</strong>{{ step.summary }}</span><small>{{ formatDuration(step.duration_ms) }}</small></div><footer><code>{{ equipmentDiagnosis.run_id }}</code><span>{{ formatDuration(equipmentDiagnosis.duration_ms) }}</span></footer></article></section>
        </template>
      </section>

      <section v-if="activeView === 'production'" class="production-view">
        <header class="production-hero">
          <div class="production-intro">
            <p class="section-code">PHASE 06 / PRODUCTION CONTROL DESK</p>
            <h2>看清达成，<br /><span>盯住趋势</span></h2>
            <p>从末工序完工口径出发，按产线与业务日聚合实际和计划，再用最近七日线性斜率描述短期方向。所有数字可回到 SQL、Recipe 和 LangGraph 节点。</p>
            <button class="production-run" :disabled="productionRunning" @click="generateProductionTrend"><span v-if="productionRunning" class="button-spinner"></span>{{ productionRunning ? '正在计算生产趋势' : productionTrend ? '重新运行生产问析' : '运行生产趋势问析' }} <b>↗</b></button>
          </div>
          <div class="production-poster" aria-hidden="true"><span>7D</span><svg viewBox="0 0 280 100"><polyline points="0,76 42,59 84,64 126,40 168,45 210,22 280,10" /></svg><small>LINEAR SLOPE<br />NOT A FORECAST</small></div>
        </header>

        <div class="production-query-strip"><span>SQL 下钻</span><button @click="openProductionQuestion('本月各产线完工产量排名')"><b>01</b> 完工产量 <i>→</i></button><button @click="openProductionQuestion('本月各产线计划达成率')"><b>02</b> 计划达成 <i>→</i></button><button @click="openProductionQuestion('最近30天每日完工产量趋势')"><b>03</b> 每日趋势 <i>→</i></button></div>
        <div v-if="productionError" class="agent-error"><strong>生产趋势未完成</strong><p>{{ productionError }}</p><button v-if="needsDeepseekConfig(productionError)" @click="activeView = 'settings'">前往模型配置</button><button v-else @click="generateProductionTrend">重新运行</button></div>
        <div v-if="productionRunning" class="production-loading"><div class="production-loader"><i v-for="n in 7" :key="n" :style="{ height: `${24 + n * 8}px` }"></i></div><div><p class="section-code">PRODUCTION RECIPE IS RUNNING</p><h3>正在核对口径并拟合七日斜率</h3><p>RAG Evidence → Safe SQL → LinearRegression → Plan Assessment → DeepSeek Brief</p></div></div>
        <section v-else-if="!productionTrend" class="production-empty"><div class="trend-index"><b>95.86</b><span>KNOWN KPI / CALCULATED LIVE</span></div><div><p class="section-code">AUDITABLE PRODUCTION WORKFLOW</p><h3>一次运行，回答“完成多少、差在哪里、方向怎样”</h3><p>页面不会读取预设结论。计划达成率和七日斜率均在运行时从末工序事实表计算。</p></div></section>

        <template v-if="productionTrend && !productionRunning">
          <section class="production-kpis">
            <article><span>FINAL OUTPUT</span><strong>{{ formatNumber(productionTrend.assessment.final_output) }}<small> 件</small></strong><p>本月末工序完工量</p></article>
            <article><span>PLAN ATTAINMENT</span><strong>{{ productionTrend.assessment.plan_attainment }}<small>%</small></strong><p>{{ formatNumber(productionTrend.assessment.planned_qty) }} 件计划</p></article>
            <article><span>BEST LINE</span><strong>{{ productionTrend.assessment.best_line.line_id }}</strong><p>{{ productionTrend.assessment.best_line.plan_attainment }}% · {{ productionTrend.assessment.best_line.line_name }}</p></article>
            <article class="attention"><span>ATTENTION LINE</span><strong>{{ productionTrend.assessment.attention_line.line_id }}</strong><p>{{ productionTrend.assessment.attention_line.plan_attainment }}% · {{ productionTrend.assessment.attention_line.slope_per_day }} 件/日</p></article>
          </section>

          <div class="production-main-grid">
            <section class="production-panel"><header><div><p class="section-code">LINE ATTAINMENT / 2025-12</p><h3>产线计划达成排名</h3></div><span>FINAL PROCESS</span></header><div class="line-rank"><article v-for="(item,index) in productionTrend.ranking" :key="item.line_id" :class="{ weak: item.line_id === productionTrend.assessment.attention_line.line_id }"><b>0{{ index + 1 }}</b><div><strong>{{ item.line_name }}</strong><span>{{ formatNumber(item.final_output) }} / {{ formatNumber(item.planned_qty) }} 件</span></div><i><em :style="{ width: `${item.plan_attainment}%` }"></em></i><small>{{ item.plan_attainment }}%</small></article></div></section>
            <section class="production-panel"><header><div><p class="section-code">DAILY FINAL OUTPUT</p><h3>29 日完工量走势</h3></div><span>REAL SQL RESULT</span></header><div class="production-chart"><div class="chart-y-title">完工产量（件）</div><div class="chart-y-ticks"><span>{{ formatNumber(productionTrendMax) }}</span><span>{{ formatNumber(productionTrendMid) }}</span><span>{{ formatNumber(productionTrendMin) }}</span></div><svg viewBox="0 0 800 260" preserveAspectRatio="none"><line v-for="y in [55,137,220]" :key="y" x1="45" :y1="y" x2="755" :y2="y" /><line class="axis-line" x1="45" y1="40" x2="45" y2="220" /><line class="axis-line" x1="45" y1="220" x2="755" y2="220" /><polyline :points="productionTrendPoints" /><circle v-for="(item,index) in productionTrend.daily_trend" :key="item.business_date" :cx="productionPointX(index)" :cy="productionPointY(item.final_output)" r="3" /></svg><div class="chart-date-axis"><span>{{ productionTrend.daily_trend[0]?.business_date.slice(5) }}</span><b>只统计 is_final_process = true</b><span>{{ productionTrend.daily_trend.at(-1)?.business_date.slice(5) }}</span></div><div class="chart-x-title">业务日期（月-日）</div></div></section>
          </div>

          <section class="slope-section"><header><div><p class="section-code">7-DAY LINEAR SLOPE</p><h3>三条产线短期方向</h3></div><p>{{ productionTrend.assessment.trend_disclaimer }}</p></header><div><article v-for="item in productionTrend.ranking" :key="item.line_id"><span>{{ item.line_id }} · {{ item.line_name }}</span><strong :class="{ down: item.slope_per_day < 0 }">{{ item.slope_per_day > 0 ? '+' : '' }}{{ item.slope_per_day }} <small>件/日</small></strong><i><em :style="{ width: `${100 * Math.abs(item.slope_per_day) / productionSlopeMax}%` }"></em></i><p>{{ item.direction }} · {{ productionTrend.period.trend_window }}</p></article></div></section>

          <div class="production-insight-grid"><section class="production-brief"><header><p class="section-code">DEEPSEEK OPERATIONS BRIEF</p><span>{{ productionTrend.brief.generation_mode.toUpperCase() }}</span></header><h3>{{ productionTrend.brief.headline }}</h3><p>{{ productionTrend.brief.summary }}</p><div><article><b>数据观察</b><ul><li v-for="item in productionTrend.brief.observations" :key="item">{{ item }}</li></ul></article><article><b>建议动作</b><ul><li v-for="item in productionTrend.brief.actions" :key="item">{{ item }}</li></ul></article></div></section><section class="production-trace"><p class="section-code">LANGGRAPH / 5 NODES</p><div v-for="(step,index) in productionTrend.trace" :key="step.node_name"><b>0{{ index + 1 }}</b><span><strong>{{ step.display_name }}</strong>{{ step.summary }}</span><small>{{ formatDuration(step.duration_ms) }}</small></div><footer><code>{{ productionTrend.run_id }}</code><span>{{ formatDuration(productionTrend.duration_ms) }}</span></footer></section></div>

          <section class="production-proof"><div><p class="section-code">RECIPE + RAG EVIDENCE</p><h3>{{ productionTrend.recipe.name }}</h3><p>{{ productionTrend.recipe.explanation_rule }}</p><span v-for="metric in productionTrend.evidence.metrics" :key="metric.code"><b>{{ metric.name }} · v{{ metric.version }}</b><code>{{ metric.formula }}</code></span><details><summary>查看审核 Feature SQL</summary><pre>{{ productionTrend.recipe.feature_sql }}</pre></details></div><aside><span>ALGORITHM</span><strong>{{ productionTrend.recipe.algorithm }}</strong><p>mode / {{ productionTrend.recipe.parameters.mode }}</p><p>fit window / {{ productionTrend.recipe.parameters.fit_days }} days</p><p>SQL tables / {{ productionTrend.evidence.tables.length }}</p></aside></section>
        </template>

        <section class="algorithm-lab"><header><div><p class="section-code">SIX REVIEWED ALGORITHM RECIPES</p><h3>算法能力验收台</h3><p>同一套真实制造数据、固定参数与时间留出；不提供任意代码执行入口。</p></div><button :disabled="algorithmRunning" @click="evaluateAlgorithms"><span v-if="algorithmRunning" class="button-spinner"></span>{{ algorithmRunning ? '六算法执行中' : algorithmSuite ? '重新执行六算法' : '执行六算法验收' }} <b>→</b></button></header><div v-if="algorithmError" class="agent-error"><strong>算法验收未完成</strong><p>{{ algorithmError }}</p></div><div v-if="algorithmSuite" class="algorithm-grid"><article v-for="(item,index) in algorithmSuite.algorithms" :key="item.algorithm"><span>0{{ index + 1 }} / {{ item.scene.toUpperCase() }}</span><h4>{{ item.algorithm }}</h4><p>{{ item.use_case }}</p><strong>{{ algorithmMetric(item.metrics) }}</strong><footer>{{ formatNumber(item.rows.training) }} TRAIN · {{ formatNumber(item.rows.validation) }} VALID</footer></article></div><footer v-if="algorithmSuite"><span>{{ algorithmSuite.passed_count }}/{{ algorithmSuite.algorithm_count }} RECIPES PASSED</span><code>{{ algorithmSuite.guardrail }}</code><b>{{ formatDuration(algorithmSuite.duration_ms) }}</b></footer></section>
      </section>

      <section v-if="activeView === 'agent'" class="agent-view">
        <header class="agent-hero">
          <div>
            <p class="section-code">PHASE 06 / RAG + SQL + SIX ALGORITHM RECIPES</p>
            <h2>一句话，<span>走完分析链路</span></h2>
            <p>不是聊天演示：问题经过业务理解、证据检索、DeepSeek Text-to-SQL、安全校验与只读执行，最后生成图表和可追溯结论。</p>
          </div>
          <div class="agent-badge"><b>3</b><span>RAG ROUTES<br />RRF FUSION</span></div>
        </header>

        <form class="query-console" @submit.prevent="runAgent">
          <div class="console-index"><span>ASK</span><strong>01</strong></div>
          <label>
            <span>制造数据问题 / 质量 · 设备 · 生产基础问析</span>
            <textarea v-model="agentQuestion" rows="2" maxlength="300" aria-label="分析问题"></textarea>
          </label>
          <button type="submit" :disabled="agentRunning">
            <span v-if="agentRunning" class="button-spinner"></span>
            {{ agentRunning ? 'Agent 分析中' : '启动智能问析' }}
            <b>{{ agentRunning ? '请稍候' : '→' }}</b>
          </button>
        </form>
        <div class="example-switcher">
          <span>QUICK TEST /</span>
          <button v-for="example in agentExamples" :key="example.code" :class="{ active: agentQuestion === example.question }" @click="chooseAgentQuestion(example.question)">
            <small>{{ example.code }}</small><b>{{ example.scene }}</b><i>→</i>
          </button>
        </div>
        <div v-if="agentRunning" class="agent-progress"><i></i><p><strong>Agent 正在检查问题并准备分析</strong><span>完整问题将继续进入 RAG、DeepSeek 与 Text-to-SQL 链路。</span></p></div>
        <section v-if="agentClarification && !agentRunning" class="clarification-card">
          <div class="clarification-index"><span>AGENT GATE</span><strong>?</strong><small>WAITING FOR USER</small></div>
          <div class="clarification-content">
            <p class="section-code">AMBIGUITY CLARIFICATION NODE</p>
            <h3>先把问题说完整，再开始查数</h3>
            <p>{{ agentClarification.prompt }}</p>
            <div class="missing-field-list"><span v-for="field in agentClarification.missing_fields" :key="field">缺少 · {{ clarificationFieldLabel(field) }}</span></div>
            <div class="clarification-options"><button v-for="option in agentClarification.options" :key="option.question" @click="continueWithClarification(option.question)"><small>{{ option.label }}</small><b>{{ option.question }}</b><i>继续问析 →</i></button></div>
          </div>
          <footer><code>{{ agentClarification.clarification_id }}</code><span>未调用 DeepSeek · 未执行 SQL</span></footer>
        </section>
        <div v-if="agentError" class="agent-error"><strong>本次执行未完成</strong><p>{{ agentError }}</p><button v-if="needsDeepseekConfig(agentError)" @click="activeView = 'settings'">前往模型配置</button><button v-else @click="runAgent">重新运行</button></div>

        <template v-if="agentResult">
          <section class="run-summary">
            <div><span>RUN STATUS</span><strong><i></i>{{ agentResult.status.toUpperCase() }}</strong></div>
            <div><span>MODEL</span><strong>{{ agentResult.model }}</strong></div>
            <div><span>SQL MODE</span><strong>{{ agentResult.generation_mode === 'deepseek' ? 'DEEPSEEK' : 'GUARDED FALLBACK' }}</strong></div>
            <div><span>DURATION</span><strong>{{ formatDuration(agentResult.duration_ms) }}</strong></div>
            <code>{{ agentResult.run_id }}</code>
          </section>

          <section class="rag-ledger">
            <div class="rag-title"><p class="section-code">HYBRID RETRIEVAL LEDGER</p><h3>EvidenceBundle 是怎么找出来的</h3><span>{{ agentResult.evidence.retrieval.strategy }}</span></div>
            <div v-for="channel in ['exact', 'fuzzy', 'vector']" :key="channel" class="rag-channel"><span>{{ channel.toUpperCase() }}</span><strong>{{ agentResult.evidence.retrieval.channel_hits[channel] ?? 0 }}</strong><small>候选命中</small></div>
            <div class="rag-reduction"><span>CONTEXT CUT</span><strong>{{ agentResult.evidence.retrieval.context_reduction_pct }}%</strong><small>相对全量上下文</small></div>
          </section>

          <section class="trace-section">
            <header><div><p class="section-code">VISIBLE EXECUTION PIPELINE</p><h3>Agent 执行轨迹</h3></div><span>{{ agentResult.trace.filter((step) => step.status === 'completed').length }} STEPS COMPLETED</span></header>
            <div class="trace-rail">
              <article v-for="(step, index) in agentResult.trace" :key="step.node_name">
                <div class="trace-number">{{ String(index + 1).padStart(2, '0') }}</div>
                <div><span>{{ step.node_name }}</span><h4>{{ step.display_name }}</h4><p>{{ step.summary }}</p></div>
                <time>{{ formatDuration(step.duration_ms) }}</time>
              </article>
            </div>
          </section>

          <div class="evidence-sql-grid">
            <section class="evidence-card">
              <header><p class="section-code">GROUNDED EVIDENCE</p><h3>本次证据包</h3></header>
              <div class="metric-proof"><span>指标口径 · v{{ agentResult.evidence.metric.version }}</span><strong>{{ agentResult.evidence.metric.name }}</strong><code>{{ agentResult.evidence.metric.formula }}</code></div>
              <div class="rule-proof"><span>强规则</span><p>{{ agentResult.evidence.rule }}</p></div>
              <div class="table-proof"><span v-for="table in agentResult.evidence.tables" :key="table">{{ table }}</span></div>
              <div v-for="relation in agentResult.evidence.relations" :key="relation.source_table" class="join-proof"><code>{{ relation.source_table }}.{{ relation.source_column }}</code><b>→ VERIFIED JOIN →</b><code>{{ relation.target_table }}.{{ relation.target_column }}</code></div>
              <div class="source-proof"><span v-for="item in agentResult.evidence.items.slice(0, 6)" :key="item.id"><b>{{ item.source_type }}</b>{{ item.title }}<small>{{ item.channels.join(' + ') }}</small></span></div>
            </section>
            <section class="sql-card">
              <header><div><p class="section-code">TEXT-TO-SQL ARTIFACT</p><h3>生成并执行的 SQL</h3></div><span><i></i>SQLGLOT {{ agentResult.sql.validation.toUpperCase() }} · REPAIR {{ agentResult.sql.repair_count }}/2</span></header>
              <pre><code>{{ agentResult.sql.text }}</code></pre>
              <footer><span>READ ONLY TRANSACTION</span><span>TIMEOUT 5S</span><span>LIMIT ≤ 100</span></footer>
            </section>
          </div>

          <section class="result-section">
            <header><div><p class="section-code">EXECUTED RESULT / NOT MOCKED</p><h3>{{ agentResult.chart.title }}</h3></div><div class="result-header-tools"><div class="date-range">{{ agentResult.time_range.start }}<b>→</b>{{ agentResult.time_range.end }}</div><div class="export-actions"><button @click="exportAgentCsv">CSV <span>结果表</span> ↓</button><button @click="exportAgentPng">PNG <span>图表</span> ↓</button></div><small v-if="exportMessage">{{ exportMessage }}</small></div></header>
            <div class="result-grid">
              <div class="yield-chart" role="img" :aria-label="agentResult.chart.title">
                <div class="chart-y-title">{{ columnLabel(agentResult.chart.y_field) }}{{ agentResult.chart.unit ? `（${agentResult.chart.unit}）` : '' }}</div>
                <div class="chart-scale"><span>{{ chartCeiling }}{{ agentResult.chart.unit }}</span><span>{{ ((chartCeiling + chartBaseline) / 2).toFixed(1) }}{{ agentResult.chart.unit }}</span><span>{{ chartBaseline }}{{ agentResult.chart.unit }}</span></div>
                <div v-if="agentResult.chart.type === 'pareto'" class="chart-y-title chart-y-title-right">累计占比（%）</div>
                <div v-if="agentResult.chart.type === 'pareto'" class="chart-scale chart-scale-right"><span>100%</span><span>50%</span><span>0%</span></div>
                <template v-if="agentResult.chart.type !== 'line'"><i class="plot-axis plot-axis-y"></i><i class="plot-axis plot-axis-x"></i></template>
                <template v-if="agentResult.chart.type === 'bar'">
                  <div v-for="(category, index) in agentResult.chart.categories" :key="category" class="bar-column">
                    <strong>{{ agentResult.chart.series[0].data[index] }}{{ agentResult.chart.unit }}</strong>
                    <div class="bar-track"><i :style="{ height: chartHeight(agentResult.chart.series[0].data[index]) }"></i></div>
                    <span>{{ category }}</span>
                  </div>
                </template>
                <div v-else-if="agentResult.chart.type === 'pareto'" class="pareto-combo">
                  <div class="pareto-combo-bars"><div v-for="(category, index) in agentResult.chart.categories" :key="category"><strong>{{ formatNumber(agentResult.chart.series[0].data[index]) }}</strong><i><em :style="{ height: chartHeight(agentResult.chart.series[0].data[index]) }"></em></i><span>{{ category }}</span></div></div>
                  <svg viewBox="0 0 800 280" preserveAspectRatio="none" aria-hidden="true"><polyline :points="paretoLinePoints" /><g v-for="(value, index) in agentResult.chart.series[1].data" :key="index"><circle :cx="agentResult.chart.series[1].data.length <= 1 ? 400 : 70 + index * 660 / (agentResult.chart.series[1].data.length - 1)" :cy="245 - 2 * value" r="6" /><text :x="agentResult.chart.series[1].data.length <= 1 ? 400 : 70 + index * 660 / (agentResult.chart.series[1].data.length - 1)" :y="230 - 2 * value">{{ value }}%</text></g></svg>
                </div>
                <svg v-else class="line-plot" viewBox="0 0 800 280" preserveAspectRatio="none" aria-hidden="true">
                  <line v-for="y in [45, 140, 235]" :key="y" x1="55" :y1="y" x2="745" :y2="y" />
                  <line class="axis-line" x1="55" y1="35" x2="55" y2="235" />
                  <line class="axis-line" x1="55" y1="235" x2="745" y2="235" />
                  <polyline :points="linePoints" />
                  <g v-for="(value, index) in agentResult.chart.series[0].data" :key="index"><circle :cx="lineX(index)" :cy="lineY(value)" r="6" /><text :x="lineX(index)" :y="lineY(value) - 13">{{ value }}</text><text class="axis-label" :x="lineX(index)" y="262">{{ agentResult.chart.categories[index].slice(5) }}</text></g>
                </svg>
                <div class="chart-x-title">{{ columnLabel(agentResult.chart.x_field) }}</div>
              </div>
              <div class="result-table-wrap">
                <table><thead><tr><th v-for="column in agentResult.result.columns" :key="column">{{ columnLabel(column) }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in agentResult.result.rows" :key="rowIndex"><td v-for="column in agentResult.result.columns" :key="column"><b v-if="column === agentResult.chart.y_field">{{ formatCell(row[column], column) }}</b><template v-else>{{ formatCell(row[column], column) }}</template></td></tr></tbody></table>
                <p>{{ agentResult.result.row_count }} ROWS · PostgreSQL 实时查询结果</p>
              </div>
            </div>
          </section>

          <section class="answer-card"><span>AGENT CONCLUSION</span><div class="quote-mark">“</div><p>{{ agentResult.answer }}</p><footer>结论基于检验数据与已发布指标口径 <b>·</b> 不推断未提供的根因</footer></section>
        </template>
      </section>

      <section v-if="activeView === 'evaluation'" class="evaluation-view">
        <header class="evaluation-hero">
          <div><p class="section-code">ANALYSIS QUALITY / EVIDENCE-BASED SCOREBOARD</p><h2>问析不是黑盒，<br /><span>每一项都能验收</span></h2><p>固定验证案例衡量 RAG，真实运行记录衡量 SQL、证据链与延迟。所有分数均由数据库计算，不让大模型给自己打分。</p><button :disabled="evaluationLoading" @click="loadEvaluation">{{ evaluationLoading ? '正在重新计算…' : '重新计算评测 →' }}</button></div>
          <aside :class="evaluation?.summary.status" :style="{ '--gate-progress': evaluation ? `${100 * evaluation.summary.passed_gates / Math.max(evaluation.summary.total_gates, 1)}%` : '0%' }">
            <header><span>QUALITY GATES</span><b>{{ evaluation?.summary.status === 'ready' ? 'READY' : evaluation?.summary.status === 'attention' ? 'ATTENTION' : 'COLLECTING' }}</b></header>
            <div class="evaluation-gate-dial"><div><small>PASSED</small><strong>{{ evaluation?.summary.passed_gates ?? '—' }}<em>/{{ evaluation?.summary.total_gates ?? '—' }}</em></strong><span>质量门禁通过</span></div></div>
            <footer>
              <div><span>REAL RUNS</span><strong>{{ evaluation?.window.runs ?? 0 }}</strong></div>
              <div><span>GATE RATE</span><strong>{{ evaluation ? Math.round(100 * evaluation.summary.passed_gates / Math.max(evaluation.summary.total_gates, 1)) : 0 }}%</strong></div>
              <i><em></em></i><small>最近真实问析样本 · 数据库实时计算</small>
            </footer>
          </aside>
        </header>

        <div v-if="evaluationLoading" class="evaluation-loading"><i></i><div><strong>正在执行固定 RAG 验证集</strong><span>同时汇总最近问析、SQL 修复与证据链记录。</span></div></div>
        <div v-if="evaluationError" class="agent-error"><strong>评测数据未完成</strong><p>{{ evaluationError }}</p><button @click="loadEvaluation">重新计算</button></div>

        <template v-if="evaluation && !evaluationLoading">
          <section class="evaluation-metrics">
            <article v-for="(metric,index) in evaluation.metrics" :key="metric.key" :class="{ passed: metric.passed }">
              <header><span>0{{ index + 1 }}</span><b>{{ metric.passed ? 'PASS' : 'CHECK' }}</b></header>
              <h3>{{ metric.label }}</h3><strong>{{ evaluationValue(metric) }}</strong>
              <div><i><em :style="{ width: evaluationBar(metric) }"></em></i><small>门槛 {{ evaluationThreshold(metric) }}</small></div>
              <p>{{ metric.description }}</p>
            </article>
          </section>

          <div class="evaluation-detail-grid">
            <section class="rag-benchmark-card">
              <header><div><p class="section-code">RAG GOLD SET / TOP {{ evaluation.rag.top_k }}</p><h3>必需表召回账本</h3></div><strong>{{ evaluation.rag.passed_cases }}/{{ evaluation.rag.case_count }}</strong></header>
              <div class="rag-benchmark-kpis"><span><b>{{ evaluation.rag.required_table_recall_pct }}%</b>必需表召回</span><span><b>{{ evaluation.rag.metric_accuracy_pct }}%</b>指标命中</span><span><b>{{ evaluation.rag.case_pass_pct }}%</b>案例通过</span></div>
              <div class="evaluation-case-list"><article v-for="item in evaluation.rag.cases" :key="item.case_code"><i :class="{ on: item.passed }"></i><span><b>{{ item.case_code }}</b>{{ item.question }}</span><small>{{ item.recalled_tables.length }}/{{ item.expected_tables.length }} TABLES</small></article></div>
            </section>

            <section class="clarification-audit-card">
              <header><p class="section-code">CLARIFICATION FUNNEL</p><h3>歧义问题拦截</h3></header>
              <div class="clarification-score"><strong>{{ evaluation.clarification.total }}</strong><span>次问题被要求补充</span></div>
              <dl><div><dt>已继续问析</dt><dd>{{ evaluation.clarification.resolved }}</dd></div><div><dt>等待补充</dt><dd>{{ evaluation.clarification.pending }}</dd></div><div><dt>澄清转化率</dt><dd>{{ evaluation.clarification.resolution_pct }}%</dd></div></dl>
              <p>歧义节点先检查场景、指标、时间、维度和目标；信息不足时不会调用 DeepSeek，也不会生成 SQL。</p>
            </section>
          </div>

          <section class="evaluation-runs">
            <header><div><p class="section-code">RECENT RUN AUDIT / LAST 10</p><h3>最近问析运行</h3></div><span>{{ evaluation.window.completed }} COMPLETED · {{ evaluation.window.failed }} FAILED</span></header>
            <div class="evaluation-run-table"><div class="evaluation-run-head"><span>状态</span><span>问题</span><span>场景 / 模型</span><span>SQL 修复</span><span>证据链</span><span>耗时</span></div><article v-for="run in evaluation.recent_runs" :key="run.run_id"><b :class="run.status">{{ run.status.toUpperCase() }}</b><span><strong>{{ run.question }}</strong><code>{{ run.run_id.slice(0, 8) }}</code></span><span>{{ run.scene }}<small>{{ run.model_id }}</small></span><span>{{ run.repair_count }}/2</span><span :class="{ complete: run.evidence_complete }">{{ run.evidence_complete ? '完整' : '缺失' }}</span><time>{{ formatDuration(run.duration_ms) }}</time></article><p v-if="!evaluation.recent_runs.length">尚无真实问析记录，完成一次智能问析后即可形成运行质量指标。</p></div>
            <footer><span>{{ evaluation.methodology }}</span><time>{{ formatDate(evaluation.generated_at) }}</time></footer>
          </section>
        </template>
      </section>

      <section v-if="activeView === 'settings'" class="model-settings-view">
        <header class="settings-hero">
          <div><p class="section-code">LOCAL MODEL CREDENTIAL / RUNTIME ONLY</p><h2>把模型连接<br /><span>留在本机</span></h2><p>比赛现场可直接配置 DeepSeek。密钥只进入后端进程内存，不写数据库、不回显、不进入 Git；Docker 重启后自动清除。</p></div>
          <aside :class="{ configured: deepseekConfig?.configured }"><i></i><span>DEEPSEEK STATUS</span><strong>{{ deepseekConfig?.configured ? 'READY' : 'SETUP' }}</strong><small>{{ deepseekConfig?.configured ? '模型通道可用' : '等待 API Key' }}</small></aside>
        </header>

        <div class="settings-layout">
          <form class="credential-card" @submit.prevent="saveDeepseekConfig">
            <header><div><p class="section-code">SECURE INPUT + MODEL ROUTE</p><h3>DeepSeek 运行配置</h3></div><span>不持久化</span></header>
            <fieldset class="model-selector">
              <legend>选择推理模型 <small>MODEL ROUTE</small></legend>
              <div class="model-options"><label v-for="model in deepseekModels" :key="model.id" :class="{ active: deepseekSelectedModel === model.id }"><input v-model="deepseekSelectedModel" type="radio" name="deepseek-model" :value="model.id" /><span><b>{{ model.name }}</b><small>{{ model.tag }}</small><code>{{ model.id }}</code><em>{{ model.description }}</em></span><i>✓</i></label></div>
              <p>模型和 Key 同属运行时配置；切换模型后会重新执行连接验证。</p>
            </fieldset>
            <label class="secret-field">
              <span>API KEY</span>
              <div><input v-model="deepseekApiKey" :type="showDeepseekApiKey ? 'text' : 'password'" autocomplete="off" spellcheck="false" placeholder="sk-••••••••••••••••" aria-label="DeepSeek API Key" /><button type="button" @click="showDeepseekApiKey = !showDeepseekApiKey">{{ showDeepseekApiKey ? '隐藏' : '显示' }}</button></div>
              <small>{{ deepseekConfig?.configured ? '留空可沿用当前内存 Key；填写新 Key 则同时替换。' : '首次配置必须填写 Key。' }}提交后输入框立即清空，服务器响应不会包含密钥或其片段。</small>
            </label>
            <div v-if="deepseekConfigError" class="config-feedback error">{{ deepseekConfigError }}</div>
            <div v-if="deepseekConfigMessage" class="config-feedback success">{{ deepseekConfigMessage }}</div>
            <footer><button class="config-save" type="submit" :disabled="deepseekConfigSaving">{{ deepseekConfigSaving ? '正在验证连接…' : '保存并验证连接 →' }}</button><button v-if="deepseekConfig?.can_clear" class="config-clear" type="button" :disabled="deepseekConfigSaving" @click="clearDeepseekConfig">清除页面配置</button></footer>
          </form>

          <section class="connection-card">
            <header><p class="section-code">CONNECTION PROFILE</p><span :class="{ on: deepseekConfig?.configured }"><i></i>{{ deepseekConfig?.configured ? 'CONFIGURED' : 'NOT CONFIGURED' }}</span></header>
            <dl><div><dt>配置来源</dt><dd>{{ deepseekSourceLabel }}</dd></div><div><dt>模型</dt><dd><code>{{ deepseekConfig?.model }}</code></dd></div><div><dt>接口地址</dt><dd><code>{{ deepseekConfig?.base_url }}</code></dd></div><div><dt>推理强度</dt><dd>{{ deepseekConfig?.reasoning_effort?.toUpperCase() }}</dd></div></dl>
            <div class="security-note"><b>安全边界</b><p>该入口仅适用于本地比赛演示。若部署到公网，应关闭此入口并使用服务端 Secret 管理与 HTTPS。</p></div>
          </section>
        </div>

        <section class="config-flow"><p class="section-code">WHAT HAPPENS AFTER SUBMIT</p><div><article><b>01</b><span><strong>浏览器提交</strong>仅发送到本机 `/api`</span></article><article><b>02</b><span><strong>后端内存保存</strong>不进入数据库和日志</span></article><article><b>03</b><span><strong>连接探测</strong>调用 DeepSeek 验证有效性</span></article><article><b>04</b><span><strong>Agent 即时启用</strong>LangGraph 读取当前 Key</span></article></div></section>
      </section>
    </template>

    <div v-if="metricEditorOpen" class="modal-backdrop" @click.self="metricEditorOpen = false"><form class="metric-editor" @submit.prevent="saveMetric"><header><div><p class="section-code">METRIC DEFINITION</p><h2>{{ editingMetric ? '编辑指标口径' : '新增指标口径' }}</h2></div><button type="button" :disabled="metricSaving" @click="metricEditorOpen = false">×</button></header><div class="form-grid"><label>指标编码<input v-model="metricForm.metric_code" :disabled="editingMetric" required pattern="[a-z][a-z0-9_]{2,48}" /></label><label>业务主题<select v-model="metricForm.topic_code"><option v-for="topic in topics" :key="topic.topic_code" :value="topic.topic_code">{{ topic.topic_name }}</option></select></label><label>指标名称<input v-model="metricForm.metric_name" required /></label><label>单位<input v-model="metricForm.unit" required /></label><label class="wide">业务说明<textarea v-model="metricForm.description" required></textarea></label><label class="wide">计算公式<textarea v-model="metricForm.formula" class="formula-input" required></textarea></label><label>统计粒度<input v-model="metricForm.grain" required /></label><label>状态<select v-model="metricForm.status"><option value="draft">草稿</option><option value="published">已发布</option><option value="disabled">已停用</option></select></label><label class="wide">可用维度（顿号分隔）<input v-model="dimensionText" /></label><label class="wide">映射表（顿号分隔）<input v-model="mappedTableText" /></label></div><div v-if="metricError" class="config-feedback error">{{ metricError }}</div><footer><button type="button" :disabled="metricSaving" @click="metricEditorOpen = false">取消</button><button class="save" type="submit" :disabled="metricSaving">{{ metricSaving ? '正在保存…' : '保存口径' }}</button></footer></form></div>
  </main>
</template>
