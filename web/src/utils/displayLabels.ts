export const sourceKindLabels: Record<string, string> = {
  daily_direction: '今日方向',
  stock_analysis: '个股分析',
  news_article: '新闻',
  announcement: '公告',
  research_report: '研报',
  manual_source: '手动材料',
  daily_trade_log: '每日操作',
  analysis_memory: '分析记忆',
}

export const originLabels: Record<string, string> = {
  user: '用户录入',
  agent: 'AI 生成',
  external: '外部来源',
  system: '系统生成',
  collector: '自动采集',
  migration: '历史迁移',
}

export const manualSubtypeLabels: Record<string, string> = {
  opinion: '观点',
  article: '文章',
  announcement: '公告',
  research_report: '研报',
  note: '笔记',
  other: '其他',
}

export const subjectTypeLabels: Record<string, string> = {
  stock: '股票',
  topic: '主题',
  portfolio: '组合',
  market: '市场',
  general: '通用',
}

export const claimTypeLabels: Record<string, string> = {
  fact: '事实',
  decision: '决策',
  thesis: '投资逻辑',
  risk: '风险',
  catalyst: '催化',
  contradiction: '矛盾',
  question: '待验证问题',
}

export const claimStatusLabels: Record<string, string> = {
  active: '有效',
  superseded: '已替代',
  contradicted: '有矛盾',
  resolved: '已解决',
  rejected: '已驳回',
}

export const pageTypeLabels: Record<string, string> = {
  stock: '股票',
  topic: '主题',
  market: '市场',
  general: '通用',
  home: '首页',
  log: '日志',
  source_digest: '来源摘要',
  analysis_run_digest: '分析运行摘要',
  stock_profile: '股票档案',
  stock_timeline: '股票时间线',
  stock_analysis_runs: '分析记录',
  daily_direction: '今日方向',
  trade_month: '月度交易记录',
  portfolio_overview: '组合概览',
  trade_review: '交易复盘',
  contradictions: '观点冲突',
  open_questions: '待验证问题',
  saved_query: '已保存问答',
}

export const polarityLabels: Record<string, string> = {
  positive: '正向',
  negative: '负向',
  neutral: '中性',
  bullish: '看多',
  bearish: '看空',
  mixed: '多空混合',
}

export const wikiSourceStatusLabels: Record<string, string> = {
  queued: '已排队',
  planning: '规划中',
  applying: '写入中',
  pending: '待处理',
  processed: '已处理',
  needs_reprocess: '需重新处理',
  failed: '失败',
  ignored: '已忽略',
}

export const wikiIngestStatusLabels: Record<string, string> = {
  queued: '已排队',
  pending: '待开始',
  planning: '规划中',
  applying: '写入中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  preview: '预览',
  skipped: '已跳过',
}

export const wikiIngestModeLabels: Record<string, string> = {
  preview: '预览',
  apply: '写入',
}

export const wikiTriggerTypeLabels: Record<string, string> = {
  source: '单个来源',
  analysis_run: '分析运行',
  batch: '批量',
  manual: '手动',
  schedule: '定时',
}

export const wikiPatchModeLabels: Record<string, string> = {
  replace: '替换',
  append: '追加',
  prepend: '前置',
}

export const wikiPageStatusLabels: Record<string, string> = {
  active: '有效',
  inactive: '停用',
  draft: '草稿',
  archived: '已归档',
  deleted: '已删除',
}

export const wikiReviewStatusLabels: Record<string, string> = {
  generated: '自动生成',
  reviewed: '已审核',
  needs_review: '待审核',
  rejected: '已驳回',
}

export const lintSeverityLabels: Record<string, string> = {
  error: '错误',
  warning: '警告',
  info: '提示',
}

export const lintStatusLabels: Record<string, string> = {
  ok: '正常',
  warning: '需关注',
  error: '异常',
}

export const lintIssueKindLabels: Record<string, string> = {
  missing_index: '缺少索引',
  missing_log: '缺少日志',
  broken_link: '断链',
  orphan_page: '孤立页面',
  missing_frontmatter: '缺少元数据',
  missing_file: '缺少文件',
  empty_page: '空页面',
  stale_page: '过期页面',
  missing_source: '缺少来源',
  uncited_claim: '未引用论断',
  stale_contradiction: '未处理矛盾',
  duplicate_claim: '重复论断',
  pending_sources: '待处理来源',
  missing_source_ids: '缺少来源 ID',
}

const tagPrefixLabels: Record<string, string> = {
  stock: '股票',
  topic: '主题',
  manual: '手动材料',
  node: '分析节点',
  source: '来源',
  date: '日期',
  trade_log: '交易记录',
  memory: '记忆',
}

const memoryKindLabels: Record<string, string> = {
  analysis: '分析记忆',
}

const analysisNodeLabels: Record<string, string> = {
  market_report: '市场分析',
  sentiment_report: '情绪分析',
  news_report: '新闻分析',
  fundamentals_report: '基本面分析',
  catalyst_report: '催化分析',
  flow_risk_report: '资金风险',
  data_quality_summary: '数据质量',
  bull_bear_debate: '多空辩论',
  trader_investment_plan: '交易计划',
  risk_debate: '风险辩论',
  final_trade_decision: '最终决策',
  full_report: '完整报告',
}

export function labelForSourceKind(value: string) {
  return sourceKindLabels[value] || value || '-'
}

export function labelForOrigin(value: string) {
  return originLabels[value] || value || '-'
}

export function labelForManualSubtype(value: string) {
  return manualSubtypeLabels[value] || value || '-'
}

export function labelForMemoryKind(value: string) {
  return memoryKindLabels[value] || value || '-'
}

export function labelForSubjectType(value: string) {
  return subjectTypeLabels[value] || value || '-'
}

export function labelForClaimType(value: string) {
  return claimTypeLabels[value] || value || '-'
}

export function labelForClaimStatus(value: string) {
  return claimStatusLabels[value] || value || '-'
}

export function labelForPolarity(value: string) {
  return polarityLabels[value] || value || '-'
}

export function labelForPageType(value: string) {
  return pageTypeLabels[value] || value || '-'
}

export function labelForWikiSourceStatus(value: string) {
  return wikiSourceStatusLabels[value] || value || '-'
}

export function labelForWikiIngestStatus(value: string) {
  return wikiIngestStatusLabels[value] || value || '-'
}

export function labelForWikiIngestMode(value: string) {
  return wikiIngestModeLabels[value] || value || '-'
}

export function labelForWikiTriggerType(value: string) {
  return wikiTriggerTypeLabels[value] || value || '-'
}

export function labelForWikiPatchMode(value: string) {
  return wikiPatchModeLabels[value] || value || '-'
}

export function labelForWikiPageStatus(value: string) {
  return wikiPageStatusLabels[value] || value || '-'
}

export function labelForWikiReviewStatus(value: string) {
  return wikiReviewStatusLabels[value] || value || '-'
}

export function labelForLintSeverity(value: string) {
  return lintSeverityLabels[value] || value || '-'
}

export function labelForLintStatus(value: string) {
  return lintStatusLabels[value] || value || '-'
}

export function labelForLintIssueKind(value: string) {
  return lintIssueKindLabels[value] || value || '-'
}

export function labelForTag(tag: string) {
  if (!tag) return '-'
  const [prefix, ...rest] = tag.split('/')
  const value = rest.join('/')
  if (!value) return tagPrefixLabels[prefix] || tag
  if (prefix === 'manual') return `手动材料：${labelForManualSubtype(value)}`
  if (prefix === 'source') return `来源：${labelForSourceKind(value)}`
  if (prefix === 'node') return `分析节点：${analysisNodeLabels[value] || value}`
  if (prefix === 'stock') return `股票：${value}`
  if (prefix === 'topic') return `主题：${value}`
  if (prefix === 'date') return `日期：${value}`
  if (prefix === 'memory') return `记忆：${labelForMemoryKind(value)}`
  return `${tagPrefixLabels[prefix] || prefix}：${value}`
}
