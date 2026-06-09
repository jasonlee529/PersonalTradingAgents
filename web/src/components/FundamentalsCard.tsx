import { Card, Grid } from '@arco-design/web-react'

const { Row, Col } = Grid

interface Props {
  fundamentals: Record<string, unknown> | null
}

const labelMap: Record<string, string> = {
  name: '名称',
  pe_ttm: 'PE(TTM)',
  pe_forward: '预测PE',
  pe_static: '静态PE',
  pb: 'PB',
  roe: 'ROE',
  roe_weighted: '加权ROE',
  revenue_growth: '营收增长',
  main_revenue_growth: '主营收入增长',
  profit_growth: '利润增长',
  net_profit_growth: '净利润增长',
  debt_ratio: '资产负债率',
  gross_margin: '毛利率',
  market_cap: '总市值',
  total_mcap: '总市值',
  float_market_cap: '流通市值',
  float_mcap: '流通市值',
  total_shares: '总股本',
  float_shares: '流通股本',
  industry: '行业',
  list_date: '上市日期',
  sources: '数据源',
  source: '数据源',
}

const priorityKeys = [
  'name',
  'industry',
  'pe_ttm',
  'pe_forward',
  'pe_static',
  'pb',
  'roe',
  'roe_weighted',
  'gross_margin',
  'revenue_growth',
  'main_revenue_growth',
  'profit_growth',
  'net_profit_growth',
  'debt_ratio',
  'market_cap',
  'total_mcap',
  'float_market_cap',
  'float_mcap',
  'total_shares',
  'float_shares',
  'list_date',
  'sources',
]

const percentKeys = new Set([
  'roe',
  'roe_weighted',
  'revenue_growth',
  'main_revenue_growth',
  'profit_growth',
  'net_profit_growth',
  'debt_ratio',
  'gross_margin',
])
const dateKeys = new Set(['list_date'])

function formatValue(key: string, value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.filter(Boolean).join(', ') || '-'
  if (dateKeys.has(key)) return String(value)
  if (typeof value === 'number' || (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value)))) {
    const num = Number(value)
    if (percentKeys.has(key)) {
      const pct = Math.abs(num) <= 1 ? num * 100 : num
      return `${pct.toFixed(2)}%`
    }
    if (Math.abs(num) >= 100000000) return `${(num / 100000000).toFixed(2)}亿`
    return Number.isInteger(num) ? num.toLocaleString() : num.toFixed(2)
  }
  return String(value)
}

export default function FundamentalsCard({ fundamentals }: Props) {
  if (!fundamentals) {
    return (
      <Card className="animate-fade-in-up stagger-3">
        <div style={{ color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center' }}>暂无基本面数据</div>
      </Card>
    )
  }

  const keys = [
    ...priorityKeys.filter((key) => key in fundamentals),
    ...Object.keys(fundamentals).filter((key) => key !== 'symbol' && !priorityKeys.includes(key)),
  ]
  const items = keys
    .map((key) => ({ label: labelMap[key] || key, value: formatValue(key, fundamentals[key]) }))
    .filter((item) => item.value !== '-')

  return (
    <Card className="animate-fade-in-up stagger-3" title="基本面指标">
      <Row gutter={[24, 16]}>
        {items.map((item) => (
          <Col span={6} key={item.label}>
            <div className="metric-card" style={{ padding: '16px 20px' }}>
              <div className="metric-label">{item.label}</div>
              <div className="metric-value">{item.value}</div>
            </div>
          </Col>
        ))}
      </Row>
    </Card>
  )
}
