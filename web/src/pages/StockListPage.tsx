import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Input, Select, Spin, Table, Tag, Message } from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { stockApi } from '../api/client'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function displayNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(digits)
}

function displayAmount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const num = Number(value)
  if (Math.abs(num) >= 100000000) return `${(num / 100000000).toFixed(2)}亿`
  if (Math.abs(num) >= 10000) return `${(num / 10000).toFixed(2)}万`
  return num.toFixed(2)
}

export default function StockListPage() {
  const navigate = useNavigate()
  const [tradeDate, setTradeDate] = useState(today())
  const [market, setMarket] = useState('all')
  const [keyword, setKeyword] = useState('')
  const [sort, setSort] = useState('change_pct_desc')
  const [minChangePct, setMinChangePct] = useState('9.5')
  const [mode, setMode] = useState<'all' | 'limitup'>('all')

  const { data, isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: mode === 'limitup'
      ? ['limit-up-filtered', tradeDate, market, keyword, minChangePct]
      : ['market-list', tradeDate, market, keyword, sort],
    queryFn: async () => {
      const resp = mode === 'limitup'
        ? await stockApi.limitUpFiltered({
          trade_date: tradeDate,
          market,
          q: keyword.trim() || undefined,
          min_change_pct: parseFloat(minChangePct),
        })
        : await stockApi.marketList({
          trade_date: tradeDate,
          market,
          q: keyword.trim() || undefined,
          sort,
        })
      return resp.data as { total: number; items: any[]; trade_date: string; market: string; error?: string }
    },
    enabled: !!tradeDate,
    staleTime: 30000,
  })

  const items = data?.items || []

  const refreshAll = async () => {
    Message.info('正在从远程刷新全市场数据...')
    try {
      await stockApi.marketListRefresh({ trade_date: tradeDate })
      await refetch()
      Message.success('全市场数据已刷新')
    } catch (e: any) {
      Message.error('刷新失败: ' + (e?.message || String(e)))
    }
  }

  const openStock = (symbol: string) => {
    navigate(`/stock?symbol=${encodeURIComponent(symbol)}`)
  }

  const columns = mode === 'limitup'
    ? [
      {
        title: '股票',
        dataIndex: 'symbol',
        width: 160,
        render: (_: unknown, item: any) => (
          <Button type="text" size="small" onClick={() => openStock(item.symbol)}>
            {item.symbol} {item.name || ''}
          </Button>
        ),
      },
      {
        title: '市场',
        dataIndex: 'market',
        width: 100,
        render: (value: string) => (
          <Tag color={value === 'sh' ? 'red' : 'arcoblue'}>{value === 'sh' ? '沪市' : '深市'}</Tag>
        ),
      },
      {
        title: '最新价',
        dataIndex: 'price',
        width: 100,
        render: (value?: number) => displayNumber(value),
      },
      {
        title: '涨跌幅',
        dataIndex: 'change_pct',
        width: 110,
        render: (value?: number) => (
          <span style={{ color: 'var(--color-up)', fontWeight: 600 }}>{displayNumber(value)}%</span>
        ),
      },
      {
        title: '成交额',
        dataIndex: 'turnover',
        width: 120,
        render: (value?: number) => displayAmount(value),
      },
      {
        title: '换手率',
        dataIndex: 'turnover_rate',
        width: 100,
        render: (value?: number) => (value === null || value === undefined) ? '-' : `${displayNumber(value)}%`,
      },
      {
        title: '涨停价',
        dataIndex: 'limit_up_price',
        width: 100,
        render: (value?: number) => displayNumber(value),
      },
    ]
    : [
      {
        title: '股票',
        dataIndex: 'symbol',
        width: 160,
        render: (_: unknown, item: any) => (
          <Button type="text" size="small" onClick={() => openStock(item.symbol)}>
            {item.symbol} {item.name || ''}
          </Button>
        ),
      },
      {
        title: '市场',
        dataIndex: 'market',
        width: 100,
        render: (value: string) => (
          <Tag color={value === 'sh' ? 'red' : 'arcoblue'}>{value === 'sh' ? '沪市' : '深市'}</Tag>
        ),
      },
      {
        title: '最新价',
        dataIndex: 'price',
        width: 100,
        render: (value?: number) => displayNumber(value),
      },
      {
        title: '涨跌幅',
        dataIndex: 'change_pct',
        width: 110,
        render: (value?: number) => {
          const num = Number(value)
          const color = num > 0 ? 'var(--color-up)' : num < 0 ? 'var(--color-down)' : 'inherit'
          return <span style={{ color, fontWeight: 600 }}>{displayNumber(value)}%</span>
        },
      },
      {
        title: '成交量',
        dataIndex: 'volume',
        width: 120,
        render: (value?: number) => value?.toLocaleString?.() || '-',
      },
      {
        title: '成交额',
        dataIndex: 'turnover',
        width: 120,
        render: (value?: number) => displayAmount(value),
      },
      {
        title: '换手率',
        dataIndex: 'turnover_rate',
        width: 100,
        render: (value?: number) => (value === null || value === undefined) ? '-' : `${displayNumber(value)}%`,
      },
      {
        title: '振幅',
        dataIndex: 'amplitude',
        width: 100,
        render: (value?: number) => (value === null || value === undefined) ? '-' : `${displayNumber(value)}%`,
      },
      {
        title: 'PE',
        dataIndex: 'pe_ratio',
        width: 90,
        render: (value?: number) => displayNumber(value),
      },
    ]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 className="page-header-title">{mode === 'limitup' ? '涨停池 (本地筛选)' : '全市场股票列表'}</h2>
          <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
            {mode === 'limitup'
              ? '从全市场行情数据中筛选出涨停/高涨幅股票，数据优先读取本地缓存文件'
              : '每个交易日自动更新全市场股票行情数据，本地文件持久化保存'}
          </div>
        </div>
        <Button
          type="primary"
          icon={<IconRefresh />}
          loading={isFetching}
          onClick={() => {
            refreshAll()
          }}
        >
          刷新数据
        </Button>
      </div>

      <Card className="card-glow-hover" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select value={mode} onChange={(v) => setMode(v as 'all' | 'limitup')} style={{ width: 180 }}>
            <Select.Option value="all">全部股票</Select.Option>
            <Select.Option value="limitup">只看涨停</Select.Option>
          </Select>

          <Input
            value={tradeDate}
            onChange={setTradeDate}
            placeholder="YYYY-MM-DD"
            style={{ width: 160 }}
          />
          <Select value={market} onChange={setMarket} style={{ width: 140 }}>
            <Select.Option value="all">全部市场</Select.Option>
            <Select.Option value="sh">沪市</Select.Option>
            <Select.Option value="sz">深市</Select.Option>
          </Select>

          {mode === 'all' && (
            <Select value={sort} onChange={setSort} style={{ width: 160 }}>
              <Select.Option value="change_pct_desc">涨跌幅 ↓</Select.Option>
              <Select.Option value="change_pct_asc">涨跌幅 ↑</Select.Option>
              <Select.Option value="turnover_desc">成交额 ↓</Select.Option>
              <Select.Option value="turnover_asc">成交额 ↑</Select.Option>
              <Select.Option value="volume_desc">成交量 ↓</Select.Option>
              <Select.Option value="price_desc">价格 ↓</Select.Option>
              <Select.Option value="price_asc">价格 ↑</Select.Option>
            </Select>
          )}

          {mode === 'limitup' && (
            <Input
              value={minChangePct}
              onChange={setMinChangePct}
              placeholder="最小涨幅%"
              style={{ width: 110 }}
            />
          )}

          <Input.Search
            value={keyword}
            onChange={setKeyword}
            placeholder="搜索代码或名称"
            style={{ width: 240 }}
            allowClear
          />
          <Tag color="orangered">{data?.total ?? 0} 只</Tag>
          <Tag color="gray">数据日期 {data?.trade_date || tradeDate}</Tag>
        </div>
      </Card>

      <Card className="card-glow-hover">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}>
            <Spin size={40} />
            <div style={{ marginTop: 16, color: 'var(--text-dim)' }}>加载股票列表...</div>
          </div>
        ) : isError ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>加载失败</div>
                <Button type="primary" onClick={() => refetch()}>重新加载</Button>
              </div>
            }
          />
        ) : items.length === 0 ? (
          <Empty
            description={
              <div>
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>
                  {data?.error ? '数据获取失败' : '暂无匹配结果'}
                </div>
                <div style={{ color: 'var(--text-dim)', marginBottom: 12 }}>
                  {data?.error || '请调整搜索条件或刷新数据'}
                </div>
                <Button type="primary" onClick={() => refreshAll()}>刷新数据</Button>
              </div>
            }
          />
        ) : (
          <Table
            rowKey="symbol"
            columns={columns}
            data={items}
            loading={isFetching}
            pagination={{ pageSize: 20, showTotal: true, sizeCanChange: true }}
            scroll={{ x: 1300 }}
          />
        )}
      </Card>
    </div>
  )
}
