import { useState } from 'react'
import { Card, Tabs, Table, Tag, Statistic, Grid, Select, Divider, Spin, Empty, Input } from '@arco-design/web-react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

const { Row, Col } = Grid

// ============================================================
// API 接口
// ============================================================

interface PriceDistributionItem {
  range: string
  count: number
  percentage: number
}

interface IndustryDistributionItem {
  name: string
  count: number
}

interface ConsecutiveStock {
  symbol: string
  name: string
  consecutive: number
  industry: string
  is_st: boolean
  price?: number | null
  change_pct?: number | null
  turnover?: number | null
  seal_amount?: number | null
  first_limit_up_time?: string | null
  last_limit_up_time?: string | null
}

interface DailyAnalysisResponse {
  trade_date: string
  market: string
  total: number
  price_distribution: PriceDistributionItem[]
  industry_distribution: IndustryDistributionItem[]
  consecutive_stocks: ConsecutiveStock[]
  statistics: {
    price_mean: number
    price_median: number
    price_min: number
    price_max: number
    turnover_mean: number
    change_pct_mean: number
    st_count: number
    consecutive_count: number
  }
  items: any[]
  error?: string
}

interface TrendResponse {
  dates: string[]
  counts: number[]
  total: number
  average: number
  max: number
  max_date: string | null
}

interface RankingItem {
  rank: number
  symbol: string
  name: string
  count: number
  is_st: boolean
  industry: string
}

interface RankingResponse {
  days: number
  market: string
  include_st: boolean
  ranking: RankingItem[]
}

interface IndustryTrendItem {
  name: string
  count: number
  trend: 'up' | 'down' | 'stable'
  daily: Array<{ date: string; count: number }>
}

interface IndustryTrendResponse {
  days: number
  market: string
  industries: IndustryTrendItem[]
}

interface ConsecutiveStatsResponse {
  days: number
  market: string
  total_limit_up: number
  probability: Array<{ days: number; probability: number; description: string }>
  recent_consecutive: ConsecutiveStock[]
}

const limitUpAnalysisApi = {
  getDailyAnalysis: (params: { trade_date?: string; market?: string }) =>
    api.get<DailyAnalysisResponse>('/limit-up-analysis/daily', { params }),
  getTrend: (params: { days?: number; market?: string }) =>
    api.get<TrendResponse>('/limit-up-analysis/trend', { params }),
  getRanking: (params: { days?: number; market?: string; include_st?: boolean; limit?: number }) =>
    api.get<RankingResponse>('/limit-up-analysis/ranking', { params }),
  getIndustryTrend: (params: { days?: number; market?: string }) =>
    api.get<IndustryTrendResponse>('/limit-up-analysis/industry-trend', { params }),
  getConsecutiveStats: (params: { days?: number; market?: string }) =>
    api.get<ConsecutiveStatsResponse>('/limit-up-analysis/consecutive-stats', { params }),
}

// ============================================================
// 工具函数
// ============================================================

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function displayNumber(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(digits)
}

function displayAmount(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const number = Number(value)
  if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(2)}亿`
  if (Math.abs(number) >= 10000) return `${(number / 10000).toFixed(2)}万`
  return number.toFixed(2)
}

// ============================================================
// 图表配置
// ============================================================

// 价格区间分布图配置
function getPriceDistributionOption(data: PriceDistributionItem[]): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: any) => {
        const d = params[0]
        const item = data[d.dataIndex]
        return `${d.name}<br/>涨停数量: ${d.value}<br/>占比: ${item.percentage}%`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.map((d) => d.range),
      axisLabel: { fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        name: '涨停数量',
        type: 'bar',
        barWidth: '60%',
        data: data.map((d) => d.count),
        itemStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#ff6b6b' },
              { offset: 1, color: '#ee5a24' },
            ],
          },
          borderRadius: [4, 4, 0, 0],
        },
        label: {
          show: true,
          position: 'top',
          formatter: (params: any) => params.value,
          fontSize: 11,
        },
      },
    ],
  }
}

// 涨停排名图配置
function getTopRankOption(data: RankingItem[]): EChartsOption {
  const displayData = data.slice(0, 15)
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: displayData.map((d) => d.name).reverse(),
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        name: '涨停次数',
        type: 'bar',
        data: displayData.map((d) => d.count).reverse(),
        itemStyle: {
          color: (params: any) => {
            const item = displayData[displayData.length - 1 - params.dataIndex]
            return item?.is_st ? '#ffa502' : '#ff4757'
          },
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: 'right',
          fontSize: 11,
        },
      },
    ],
  }
}

// 每日涨停趋势图配置
function getDailyTrendOption(data: TrendResponse): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const d = params[0]
        return `${d.name}<br/>涨停数量: ${d.value}`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.dates,
      axisLabel: {
        fontSize: 10,
        rotate: 45,
        formatter: (value: string) => value.substring(5),
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 11 },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', start: 0, end: 100, height: 20, bottom: 0 },
    ],
    series: [
      {
        name: '涨停数量',
        type: 'line',
        data: data.counts,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#ff4757', width: 2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(255, 71, 87, 0.4)' },
              { offset: 1, color: 'rgba(255, 71, 87, 0.05)' },
            ],
          },
        },
        markLine: {
          data: [
            {
              name: '高热度线',
              yAxis: 100,
              lineStyle: { color: '#ff6348', type: 'dashed' },
              label: { formatter: '高热度 (100只)', position: 'end' },
            },
          ],
        },
      },
    ],
  }
}

// 行业分布图配置
function getIndustryOption(data: IndustryDistributionItem[]): EChartsOption {
  const displayData = data.slice(0, 10)
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: displayData.map((d) => d.name).reverse(),
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        name: '涨停次数',
        type: 'bar',
        data: displayData.map((d) => d.count).reverse(),
        itemStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: '#5f27cd' },
              { offset: 1, color: '#341f97' },
            ],
          },
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: 'right',
          fontSize: 11,
        },
      },
    ],
  }
}

// 连板概率图配置
function getConsecutiveProbabilityOption(data: Array<{ days: number; probability: number; description: string }>): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: any) => {
        const d = params[0]
        return `${d.name}<br/>概率: ${d.value}%`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.map((d) => d.description),
      axisLabel: { fontSize: 11, rotate: 30 },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: '{value}%',
        fontSize: 11,
      },
    },
    series: [
      {
        name: '连板概率',
        type: 'bar',
        barWidth: '60%',
        data: data.map((d) => d.probability),
        itemStyle: {
          color: (params: any) => {
            const colors = ['#ff4757', '#ff6348', '#ff7f50', '#ffa502', '#eccc68', '#7bed9f', '#70a1ff', '#5352ed', '#a55eea', '#8854d0']
            return colors[params.dataIndex % colors.length]
          },
          borderRadius: [4, 4, 0, 0],
        },
        label: {
          show: true,
          position: 'top',
          formatter: (params: any) => `${params.value}%`,
          fontSize: 11,
        },
      },
    ],
  }
}

// ============================================================
// 主页面组件
// ============================================================

export default function LimitUpAnalysisPage() {
  const [tradeDate, setTradeDate] = useState(today())
  const [market, setMarket] = useState('all')
  const [trendDays, setTrendDays] = useState(30)
  const [rankingDays, setRankingDays] = useState(30)
  const [includeST, setIncludeST] = useState(true)

  // 获取每日分析数据
  const dailyQuery = useQuery({
    queryKey: ['limit-up-daily', tradeDate, market],
    queryFn: async () => {
      const resp = await limitUpAnalysisApi.getDailyAnalysis({ trade_date: tradeDate, market })
      return resp.data
    },
    enabled: !!tradeDate,
    staleTime: 60000,
  })

  // 获取趋势数据
  const trendQuery = useQuery({
    queryKey: ['limit-up-trend', trendDays, market],
    queryFn: async () => {
      const resp = await limitUpAnalysisApi.getTrend({ days: trendDays, market })
      return resp.data
    },
    staleTime: 60000,
  })

  // 获取排名数据
  const rankingQuery = useQuery({
    queryKey: ['limit-up-ranking', rankingDays, market, includeST],
    queryFn: async () => {
      const resp = await limitUpAnalysisApi.getRanking({ days: rankingDays, market, include_st: includeST, limit: 30 })
      return resp.data
    },
    staleTime: 60000,
  })

  // 获取行业趋势数据
  const industryQuery = useQuery({
    queryKey: ['limit-up-industry', market],
    queryFn: async () => {
      const resp = await limitUpAnalysisApi.getIndustryTrend({ days: 7, market })
      return resp.data
    },
    staleTime: 60000,
  })

  // 获取连板统计数据
  const consecutiveQuery = useQuery({
    queryKey: ['limit-up-consecutive', market],
    queryFn: async () => {
      const resp = await limitUpAnalysisApi.getConsecutiveStats({ days: 60, market })
      return resp.data
    },
    staleTime: 60000,
  })

  const dailyData = dailyQuery.data
  const trendData = trendQuery.data
  const rankingData = rankingQuery.data
  const industryData = industryQuery.data
  const consecutiveData = consecutiveQuery.data

  // 涨停排名表格列
  const rankColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 70,
      render: (value: number) => (
        <Tag color={value <= 3 ? 'red' : value <= 10 ? 'orange' : 'gray'}>{value}</Tag>
      ),
    },
    {
      title: '代码',
      dataIndex: 'symbol',
      width: 100,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 120,
      render: (value: string, item: RankingItem) => (
        <span style={{ color: item.is_st ? '#ffa502' : 'inherit' }}>
          {item.is_st ? `*${value}` : value}
        </span>
      ),
    },
    {
      title: '涨停次数',
      dataIndex: 'count',
      width: 100,
      sorter: (a: RankingItem, b: RankingItem) => a.count - b.count,
      render: (value: number) => <Tag color="red">{value}</Tag>,
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 120,
    },
  ]

  // 连板个股表格列
  const consecutiveColumns = [
    {
      title: '代码',
      dataIndex: 'symbol',
      width: 100,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 120,
      render: (value: string, item: ConsecutiveStock) => (
        <span style={{ color: item.is_st ? '#ffa502' : 'inherit' }}>
          {item.is_st ? `*${value}` : value}
        </span>
      ),
    },
    {
      title: '连板数',
      dataIndex: 'consecutive',
      width: 100,
      render: (value: number) => (
        <Tag color={value >= 4 ? 'red' : value >= 3 ? 'orange' : 'blue'}>{value}连板</Tag>
      ),
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 120,
    },
    {
      title: '最新价',
      dataIndex: 'price',
      width: 100,
      render: (value?: number | null) => displayNumber(value),
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      width: 100,
      render: (value?: number | null) => (
        <span style={{ color: 'var(--color-up)', fontWeight: 600 }}>{displayNumber(value)}%</span>
      ),
    },
  ]

  const isLoading = dailyQuery.isLoading || trendQuery.isLoading || rankingQuery.isLoading
  const hasError = dailyQuery.isError || trendQuery.isError || rankingQuery.isError

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">涨停板探索性分析</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            A股市场涨停板个股数据深度挖掘 · 每日更新
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <Input
            value={tradeDate}
            onChange={setTradeDate}
            placeholder="YYYY-MM-DD"
            style={{ width: 160 }}
          />
          <Select value={market} onChange={setMarket} style={{ width: 150 }}>
            <Select.Option value="all">全部主板</Select.Option>
            <Select.Option value="sh">沪市主板</Select.Option>
            <Select.Option value="sz">深市主板</Select.Option>
          </Select>
        </div>
      </div>

      {/* 统计概览 */}
      {dailyData && !dailyData.error && (
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={6}>
            <Card className="card-glow-hover">
              <Statistic
                title="今日涨停"
                value={dailyData.total}
                suffix="只"
                style={{ fontSize: 28 }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card className="card-glow-hover">
              <Statistic
                title="ST股数量"
                value={dailyData.statistics.st_count}
                suffix="只"
                style={{ fontSize: 28, color: '#ffa502' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card className="card-glow-hover">
              <Statistic
                title="连板股数量"
                value={dailyData.statistics.consecutive_count}
                suffix="只"
                style={{ fontSize: 28, color: '#ff4757' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card className="card-glow-hover">
              <Statistic
                title="平均价格"
                value={dailyData.statistics.price_mean}
                suffix="元"
                precision={2}
                style={{ fontSize: 28 }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 主要分析标签页 */}
      <Card className="card-glow-hover">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>加载涨停分析数据...</div>
          </div>
        ) : hasError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>加载失败</div>
                <div style={{ color: 'var(--text-dim)' }}>无法获取涨停分析数据，请稍后重试</div>
              </div>
            }
          />
        ) : (
          <Tabs defaultActiveTab="overview">
            {/* 概览标签页 */}
            <Tabs.TabPane key="overview" title="市场概览">
              <div style={{ padding: '20px 0' }}>
                {/* 价格区间分布 */}
                {dailyData && dailyData.price_distribution.length > 0 && (
                  <div style={{ marginBottom: 32 }}>
                    <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>
                      涨停股价格区间分布
                    </h3>
                    <div style={{ height: 400 }}>
                      <ReactECharts option={getPriceDistributionOption(dailyData.price_distribution)} style={{ height: '100%' }} />
                    </div>
                  </div>
                )}

                <Divider />

                {/* 每日涨停趋势 */}
                {trendData && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                      <h3 style={{ fontSize: 16, fontWeight: 600 }}>
                        每日涨停数量趋势
                      </h3>
                      <Select value={trendDays} onChange={setTrendDays} style={{ width: 120 }}>
                        <Select.Option value={7}>最近7天</Select.Option>
                        <Select.Option value={30}>最近30天</Select.Option>
                        <Select.Option value={60}>最近60天</Select.Option>
                        <Select.Option value={90}>最近90天</Select.Option>
                      </Select>
                    </div>
                    <div style={{ height: 400 }}>
                      <ReactECharts option={getDailyTrendOption(trendData)} style={{ height: '100%' }} />
                    </div>
                    <Row gutter={16} style={{ marginTop: 16 }}>
                      <Col span={8}>
                        <Statistic title="总涨停次数" value={trendData.total} suffix="次" />
                      </Col>
                      <Col span={8}>
                        <Statistic title="日均涨停" value={trendData.average} suffix="只" precision={1} />
                      </Col>
                      <Col span={8}>
                        <div>
                          <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 4 }}>单日最高</div>
                          <div style={{ fontSize: 24, fontWeight: 600, color: '#ff4757' }}>
                            {trendData.max} <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>只 ({trendData.max_date || '-'})</span>
                          </div>
                        </div>
                      </Col>
                    </Row>
                  </div>
                )}
              </div>
            </Tabs.TabPane>

            {/* 涨停排名标签页 */}
            <Tabs.TabPane key="ranking" title="涨停排名">
              <div style={{ padding: '20px 0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h3 style={{ fontSize: 16, fontWeight: 600 }}>
                    涨停板排名（最近{rankingDays}天）
                  </h3>
                  <div style={{ display: 'flex', gap: 12 }}>
                    <Select value={rankingDays} onChange={setRankingDays} style={{ width: 120 }}>
                      <Select.Option value={7}>最近7天</Select.Option>
                      <Select.Option value={30}>最近30天</Select.Option>
                      <Select.Option value={60}>最近60天</Select.Option>
                      <Select.Option value={90}>最近90天</Select.Option>
                    </Select>
                    <Select value={includeST ? 'all' : 'no_st'} onChange={(v) => setIncludeST(v === 'all')} style={{ width: 120 }}>
                      <Select.Option value="all">含ST股</Select.Option>
                      <Select.Option value="no_st">剔除ST股</Select.Option>
                    </Select>
                  </div>
                </div>
                {rankingData && rankingData.ranking.length > 0 ? (
                  <div style={{ display: 'flex', gap: 24 }}>
                    <div style={{ flex: 1, height: 500 }}>
                      <ReactECharts option={getTopRankOption(rankingData.ranking)} style={{ height: '100%' }} />
                    </div>
                    <div style={{ width: 450 }}>
                      <Table
                        columns={rankColumns}
                        data={rankingData.ranking}
                        pagination={{ pageSize: 15 }}
                        size="small"
                        scroll={{ y: 450 }}
                      />
                    </div>
                  </div>
                ) : (
                  <Empty description="暂无排名数据" />
                )}
              </div>
            </Tabs.TabPane>

            {/* 行业分析标签页 */}
            <Tabs.TabPane key="industry" title="行业分布">
              <div style={{ padding: '20px 0' }}>
                {/* 当日行业分布 */}
                {dailyData && dailyData.industry_distribution.length > 0 && (
                  <div style={{ marginBottom: 32 }}>
                    <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>
                      {tradeDate} 涨停行业分布
                    </h3>
                    <div style={{ height: 400 }}>
                      <ReactECharts option={getIndustryOption(dailyData.industry_distribution)} style={{ height: '100%' }} />
                    </div>
                  </div>
                )}

                <Divider />

                {/* 近期行业热点 */}
                {industryData && industryData.industries.length > 0 && (
                  <div>
                    <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>
                      近期板块涨停热度（滚动{industryData.days}日）
                    </h3>
                    <Row gutter={16}>
                      {industryData.industries.slice(0, 10).map((item) => (
                        <Col span={4} key={item.name} style={{ marginBottom: 16 }}>
                          <Card
                            size="small"
                            className="card-glow-hover"
                            style={{
                              borderLeft: `3px solid ${item.trend === 'up' ? '#00b894' : item.trend === 'down' ? '#ff4757' : '#ffa502'}`,
                            }}
                          >
                            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{item.name}</div>
                            <div style={{ fontSize: 24, fontWeight: 700, color: '#ff4757' }}>{item.count}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                              {item.trend === 'up' ? '↑ 上升' : item.trend === 'down' ? '↓ 下降' : '→ 平稳'}
                            </div>
                          </Card>
                        </Col>
                      ))}
                    </Row>
                  </div>
                )}
              </div>
            </Tabs.TabPane>

            {/* 连板分析标签页 */}
            <Tabs.TabPane key="consecutive" title="连板分析">
              <div style={{ padding: '20px 0' }}>
                {/* 连板概率 */}
                {consecutiveData && consecutiveData.probability.length > 0 && (
                  <div style={{ marginBottom: 32 }}>
                    <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>
                      个股连续涨停概率分析
                    </h3>
                    <div style={{ height: 400 }}>
                      <ReactECharts option={getConsecutiveProbabilityOption(consecutiveData.probability)} style={{ height: '100%' }} />
                    </div>
                    <div style={{ marginTop: 16, color: 'var(--text-muted)', fontSize: 13 }}>
                      <p>• 首次涨停后，第二天连续涨停的概率约28.5%</p>
                      <p>• 连续7-10板的概率接近0，"有三必有五，有五必成妖"的说法从数据看概率较低</p>
                    </div>
                  </div>
                )}

                <Divider />

                {/* 近期连板个股 */}
                {consecutiveData && consecutiveData.recent_consecutive.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                      <h3 style={{ fontSize: 16, fontWeight: 600 }}>
                        近期连板个股池
                      </h3>
                      <Tag color="blue">共 {consecutiveData.recent_consecutive.length} 只连板股</Tag>
                    </div>
                    <Table
                      columns={consecutiveColumns}
                      data={consecutiveData.recent_consecutive}
                      pagination={{ pageSize: 10 }}
                      size="small"
                      scroll={{ y: 400 }}
                    />
                  </div>
                )}
              </div>
            </Tabs.TabPane>

            {/* 今日详情标签页 */}
            <Tabs.TabPane key="detail" title="今日详情">
              <div style={{ padding: '20px 0' }}>
                {dailyData && dailyData.items.length > 0 ? (
                  <Table
                    rowKey="symbol"
                    columns={[
                      { title: '代码', dataIndex: 'symbol', width: 100 },
                      { title: '名称', dataIndex: 'name', width: 120 },
                      {
                        title: '最新价',
                        dataIndex: 'price',
                        width: 100,
                        render: (v: number) => displayNumber(v),
                      },
                      {
                        title: '涨跌幅',
                        dataIndex: 'change_pct',
                        width: 100,
                        render: (v: number) => (
                          <span style={{ color: 'var(--color-up)', fontWeight: 600 }}>{displayNumber(v)}%</span>
                        ),
                      },
                      {
                        title: '成交额',
                        dataIndex: 'turnover',
                        width: 110,
                        render: (v: number) => displayAmount(v),
                      },
                      {
                        title: '首次封板',
                        dataIndex: 'first_limit_up_time',
                        width: 110,
                        render: (v: string) => v || '-',
                      },
                      {
                        title: '最后封板',
                        dataIndex: 'last_limit_up_time',
                        width: 110,
                        render: (v: string) => v || '-',
                      },
                      {
                        title: '封单金额',
                        dataIndex: 'seal_amount',
                        width: 110,
                        render: (v: number) => displayAmount(v),
                      },
                      {
                        title: '连板',
                        dataIndex: 'consecutive_days',
                        width: 80,
                        render: (v: number) => v ? `${v}板` : '-',
                      },
                    ]}
                    data={dailyData.items}
                    pagination={{ pageSize: 20, showTotal: true }}
                    scroll={{ x: 1000 }}
                  />
                ) : (
                  <Empty description="暂无今日涨停数据" />
                )}
              </div>
            </Tabs.TabPane>
          </Tabs>
        )}
      </Card>
    </div>
  )
}
