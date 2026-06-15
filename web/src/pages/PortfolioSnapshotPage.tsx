import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Input, Message } from '@arco-design/web-react'
import { IconSave } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import DataList from '../components/DataList'
import EmptyState from '../components/EmptyState'
import { portfolioApi, rawApi } from '../api/client'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'

const TextArea = Input.TextArea

function today() {
  return new Date().toISOString().slice(0, 10)
}

function numberText(value: number | null | undefined, digits = 2) {
  return value == null ? '' : value.toFixed(digits)
}

function calcPnl(row: HoldingDetail) {
  const quantity = row.position?.quantity ?? 0
  const avgCost = row.position?.avg_cost ?? 0
  const currentPrice = row.position?.current_price
  if (currentPrice == null || quantity <= 0) return null
  return (currentPrice - avgCost) * quantity
}

function buildMarkdown(date: string, holdings: HoldingDetail[], operationNote: string) {
  const lines = [
    `# ${date} 持仓快照`,
    '',
    '## 当天操作',
    '',
    operationNote.trim() || '无',
    '',
    '## 当前持仓',
    '',
    '| 代码 | 名称 | 市场 | 数量 | 成本价 | 当前价 | 市值 | 收益 | 收益率 |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|',
  ]

  holdings.forEach((row) => {
    const quantity = row.position?.quantity ?? 0
    const avgCost = row.position?.avg_cost ?? 0
    const currentPrice = row.position?.current_price
    const marketValue = row.position?.market_value ?? (currentPrice == null ? null : currentPrice * quantity)
    const pnl = calcPnl(row)
    const pnlPct = pnl == null || avgCost <= 0 || quantity <= 0 ? null : pnl / (avgCost * quantity) * 100
    lines.push([
      row.holding.symbol,
      row.holding.name || '',
      row.holding.market,
      String(quantity),
      numberText(avgCost, 3),
      numberText(currentPrice, 3),
      numberText(marketValue, 2),
      numberText(pnl, 2),
      pnlPct == null ? '' : `${pnlPct.toFixed(2)}%`,
    ].join(' | ').replace(/^/, '| ').replace(/$/, ' |'))
  })

  const totalValue = holdings.reduce((sum, row) => {
    const quantity = row.position?.quantity ?? 0
    const price = row.position?.current_price
    return sum + (row.position?.market_value ?? (price == null ? 0 : price * quantity))
  }, 0)
  const totalPnl = holdings.reduce((sum, row) => sum + (calcPnl(row) ?? 0), 0)
  lines.push('', '## 汇总', '', `- 持仓数量：${holdings.length}`, `- 总市值：${totalValue.toFixed(2)}`, `- 浮动收益：${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}`)
  return lines.join('\n')
}

export default function PortfolioSnapshotPage() {
  const navigate = useNavigate()
  const { setHoldings } = usePortfolioStore()
  const [snapshotDate, setSnapshotDate] = useState(today())
  const [operationNote, setOperationNote] = useState('')

  const { data } = useQuery({
    queryKey: ['holdings'],
    queryFn: async () => {
      const resp = await portfolioApi.list()
      return resp.data as HoldingDetail[]
    },
  })

  const holdings = data || []

  useEffect(() => {
    if (data) setHoldings(data)
  }, [data, setHoldings])

  const markdown = useMemo(() => buildMarkdown(snapshotDate, holdings, operationNote), [snapshotDate, holdings, operationNote])

  const saveMutation = useMutation({
    mutationFn: () => rawApi.create({
      source_kind: 'manual_source',
      origin: 'user',
      title: `${snapshotDate} 持仓快照`,
      markdown,
      metadata: {
        trade_date: snapshotDate,
        symbols: holdings.map((row) => row.holding.symbol),
        tags: ['portfolio_snapshot', `date/${snapshotDate}`, ...holdings.map((row) => `stock/${row.holding.symbol}`)],
        operation_note: operationNote,
      },
    }),
    onSuccess: (resp) => {
      Message.success('持仓快照已保存')
      navigate(`/knowledge/raw/${encodeURIComponent(resp.data.source_id)}`)
    },
    onError: (err: any) => Message.error(err?.response?.data?.detail || '保存失败'),
  })

  const columns = [
    { title: '代码', dataIndex: 'symbol', width: 90, render: (_: unknown, row: HoldingDetail) => row.holding.symbol },
    { title: '名称', dataIndex: 'name', width: 120, render: (_: unknown, row: HoldingDetail) => row.holding.name || '-' },
    { title: '数量', dataIndex: 'quantity', width: 90, render: (_: unknown, row: HoldingDetail) => row.position?.quantity?.toLocaleString() ?? 0 },
    { title: '成本价', dataIndex: 'avg_cost', width: 100, render: (_: unknown, row: HoldingDetail) => numberText(row.position?.avg_cost, 3) || '-' },
    { title: '当前价', dataIndex: 'current_price', width: 100, render: (_: unknown, row: HoldingDetail) => numberText(row.position?.current_price, 3) || '-' },
    { title: '市值', dataIndex: 'market_value', width: 110, render: (_: unknown, row: HoldingDetail) => numberText(row.position?.market_value, 2) || '-' },
    {
      title: '收益',
      dataIndex: 'unrealized_pnl',
      width: 110,
      render: (_: unknown, row: HoldingDetail) => {
        const pnl = calcPnl(row)
        if (pnl == null) return '-'
        return <span style={{ color: pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span>
      },
    },
  ]

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="page-header-title">持仓快照</h2>
        <Button type="primary" icon={<IconSave />} loading={saveMutation.isPending} onClick={() => saveMutation.mutate()} disabled={holdings.length === 0}>保存 Markdown</Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(360px, 0.8fr)', gap: 20, alignItems: 'start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <Card title="当天操作描述">
            <Input value={snapshotDate} onChange={setSnapshotDate} placeholder="YYYY-MM-DD" style={{ width: 160, marginBottom: 12 }} />
            <TextArea rows={8} value={operationNote} onChange={setOperationNote} placeholder="描述今天做了什么操作、为什么操作、后续观察点。可以直接按券商 App 的实际结果填写。" />
          </Card>

          <Card title="当前持仓">
            {holdings.length === 0 ? (
              <EmptyState icon="📊" title="暂无持仓" description="先在我的持仓里添加持仓，再生成快照。" />
            ) : (
              <DataList columns={columns} data={holdings} rowKey={(r: HoldingDetail) => r.holding.symbol} pagination={false} />
            )}
          </Card>
        </div>

        <Card title="Markdown 预览">
          <div className="report-content" style={{ minHeight: 560, maxHeight: 'calc(100vh - 210px)', overflow: 'auto', padding: 18, border: '1px solid var(--border-subtle)', borderRadius: 8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </div>
        </Card>
      </div>
    </div>
  )
}
