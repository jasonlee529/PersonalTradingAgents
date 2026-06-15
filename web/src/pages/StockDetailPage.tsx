import { lazy, Suspense, useEffect } from 'react'
import { Button, Card, Select, Spin, Grid, Typography } from '@arco-design/web-react'
import { IconRobot } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { stockApi } from '../api/client'
import { usePortfolioStore } from '../store/usePortfolioStore'
import { useStockStore, type KlineRecord, type Quote, type Fundamentals, type NewsItem } from '../store/useStockStore'
import FundamentalsCard from '../components/FundamentalsCard'
import NewsList from '../components/NewsList'

const { Row, Col } = Grid
const { Text } = Typography
const KlineChart = lazy(() => import('../components/KlineChart'))

export default function StockDetailPage() {
  const { holdings, selectedSymbol, setSelectedSymbol } = usePortfolioStore()
  const { quote, kline, fundamentals, indicators, news, announcements, researchReports, setQuote, setKline, setFundamentals, setIndicators, setNews, setAnnouncements, setResearchReports, reset } = useStockStore()
  const selectedHolding = holdings.find((h) => h.holding.symbol === selectedSymbol)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const urlSymbol = searchParams.get('symbol')?.trim() || ''

  useEffect(() => {
    if (urlSymbol && urlSymbol !== selectedSymbol) {
      setSelectedSymbol(urlSymbol)
      return
    }
    if (!urlSymbol && !selectedSymbol && holdings.length > 0) {
      setSelectedSymbol(holdings[0].holding.symbol)
    }
  }, [urlSymbol, selectedSymbol, holdings, setSelectedSymbol])

  useEffect(() => {
    return () => {
      reset()
    }
  }, [reset])

  const { isLoading } = useQuery({
    queryKey: ['snapshot', selectedSymbol],
    queryFn: async () => {
      if (!selectedSymbol) return null
      const resp = await stockApi.snapshot(selectedSymbol)
      const data = resp.data as {
        quote: Quote
        kline: KlineRecord[]
        fundamentals: Fundamentals
        indicators: { indicators?: Record<string, unknown> } | Record<string, unknown> | null
        news: NewsItem[]
        announcements: NewsItem[]
        research_reports: NewsItem[]
      }
      const rawIndicators = data.indicators
      const indicatorValues =
        rawIndicators && typeof rawIndicators === 'object' && 'indicators' in rawIndicators
          ? (rawIndicators as { indicators?: Record<string, unknown> }).indicators || null
          : rawIndicators as Record<string, unknown> | null
      setQuote(data.quote)
      setKline(data.kline)
      setFundamentals(data.fundamentals)
      setIndicators(indicatorValues)
      setNews(data.news)
      setAnnouncements(data.announcements)
      setResearchReports(data.research_reports || [])
      return data
    },
    enabled: !!selectedSymbol,
  })

  if (!selectedSymbol) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <Text type="secondary">请先添加持仓，或从涨停池选择股票</Text>
      </div>
    )
  }

  const priceColor = quote && quote.change_pct >= 0 ? 'var(--color-up)' : 'var(--color-down)'
  const displayName = fundamentals?.name || quote?.name || selectedHolding?.holding.name || selectedSymbol

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-header-title">股票详情</h2>
          <div style={{ marginTop: 4, fontSize: 14, fontWeight: 600, color: priceColor }}>
            {displayName} ({selectedSymbol})
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <Button
            type="primary"
            icon={<IconRobot />}
            onClick={() => navigate(`/analysis?symbol=${selectedSymbol}`)}
          >
            AI 分析
          </Button>
          <Select
            style={{ width: 220 }}
            placeholder="选择股票"
            value={selectedSymbol}
            onChange={(value) => setSelectedSymbol(value)}
          >
            {holdings.map((h) => (
              <Select.Option key={h.holding.symbol} value={h.holding.symbol}>
                {h.holding.symbol} - {h.holding.name}
              </Select.Option>
            ))}
          </Select>
        </div>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Spin size={40} />
        </div>
      ) : (
        <>
          <div
            style={{ marginBottom: 32 }}
            className="animate-fade-in-up stagger-1 metric-card-grid"
          >
            <div className="metric-card" style={{ borderLeft: `3px solid ${priceColor}` }}>
              <div className="metric-label">最新价</div>
              <div className="metric-value" style={{ color: priceColor, fontFamily: 'var(--font-mono)' }}>
                {quote?.price?.toFixed(2) ?? '-'}
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">开盘价</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>{quote?.open?.toFixed(2) ?? '-'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">昨收</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>{quote?.prev_close?.toFixed(2) ?? '-'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">最高价</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>{quote?.high?.toFixed(2) ?? '-'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">最低价</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>{quote?.low?.toFixed(2) ?? '-'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">成交量</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>{quote?.volume?.toLocaleString() ?? '-'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">涨跌幅</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)', color: priceColor }}>
                {quote?.change_pct !== undefined ? `${quote.change_pct.toFixed(2)}%` : '-'}
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">成交额</div>
              <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>
                {quote?.turnover ? `${(quote.turnover / 100000000).toFixed(2)}亿` : '-'}
              </div>
            </div>
          </div>

          <Row gutter={[20, 20]} style={{ marginBottom: 32 }}>
            <Col span={24}>
              <Card className="animate-fade-in-up stagger-2 card-glow-hover" title="K线图" bodyStyle={{ padding: '20px 12px' }}>
                <Suspense fallback={<Spin />}>
                  <KlineChart data={kline} />
                </Suspense>
              </Card>
            </Col>
          </Row>

          <div style={{ marginBottom: 32 }}>
            <FundamentalsCard fundamentals={fundamentals} />
          </div>

          <Card style={{ marginBottom: 24 }} className="animate-fade-in-up stagger-4 card-glow-hover" title="技术指标">
            {indicators && Object.keys(indicators).length > 0 ? (
              <Row gutter={[16, 16]}>
                {Object.entries(indicators).map(([key, value]) => {
                  const labelMap: Record<string, string> = {
                    macd: 'MACD',
                    macd_signal: 'MACD 信号线',
                    macd_hist: 'MACD 柱状图',
                    rsi: 'RSI (14)',
                    sma_5: 'SMA 5',
                    sma_10: 'SMA 10',
                    sma_20: 'SMA 20',
                    sma_60: 'SMA 60',
                    sma_120: 'SMA 120',
                    ema_12: 'EMA 12',
                    ema_20: 'EMA 20',
                    ema_60: 'EMA 60',
                    bb_upper: '布林上轨',
                    bb_middle: '布林中轨',
                    bb_lower: '布林下轨',
                    kdj_k: 'KDJ K',
                    kdj_d: 'KDJ D',
                    kdj_j: 'KDJ J',
                    cci: 'CCI',
                    wr: 'WR',
                    atr: 'ATR',
                    obv: 'OBV',
                    volume_ratio: '量比',
                    change_pct: '日涨跌幅',
                    volatility_20: '20日波动率',
                    trend_gap_20: '偏离SMA20',
                  }
                  const num = typeof value === 'number' ? value : Number(value)
                  const color = key === 'rsi' ? (num > 70 ? 'var(--color-down)' : num < 30 ? 'var(--color-up)' : 'var(--text-muted)') : undefined
                  return (
                    <Col span={6} key={key}>
                      <div className="metric-card" style={{ padding: '16px 20px' }}>
                        <div className="metric-label">{labelMap[key] || key}</div>
                        <div className="metric-value" style={{ fontSize: 20, color }}>
                          {Number.isFinite(num) ? num.toFixed(4) : String(value)}
                        </div>
                      </div>
                    </Col>
                  )
                })}
              </Row>
            ) : (
              <Text type="secondary">暂无指标数据</Text>
            )}
          </Card>

          <Card style={{}} className="animate-fade-in-up stagger-5 card-glow-hover" title="资讯">
            <NewsList news={news} announcements={announcements} researchReports={researchReports} />
          </Card>
        </>
      )}

    </div>
  )
}
