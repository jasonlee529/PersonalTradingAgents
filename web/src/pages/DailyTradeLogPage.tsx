import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Input, Message, Select, Tag } from '@arco-design/web-react'
import { IconDelete, IconPlus, IconSave } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import { portfolioApi, rawApi, type DailyTradeEntry, type PositionOverride } from '../api/client'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'

const TextArea = Input.TextArea

const actionOptions = [
  { label: '买入', value: 'buy' },
  { label: '卖出', value: 'sell' },
  { label: '加仓', value: 'add' },
  { label: '减仓', value: 'reduce' },
  { label: '清仓', value: 'clear' },
  { label: '持有', value: 'hold' },
  { label: '观察', value: 'watch' },
]

const actionLabel: Record<string, string> = Object.fromEntries(actionOptions.map((item) => [item.value, item.label]))

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function newEntry(): DailyTradeEntry {
  return {
    symbol: '',
    name: '',
    action: 'buy',
    quantity: 0,
    price: 0,
    reason: '',
    linked_analysis_run_id: '',
    linked_source_ids: [],
  }
}

function amount(entry: DailyTradeEntry): number {
  return Number(entry.quantity || 0) * Number(entry.price || 0)
}

function buildPreview(tradeDate: string, entries: DailyTradeEntry[], overrides: PositionOverride[], notes: string): string {
  const lines = [
    `# ${tradeDate} 每日操作记录`,
    '',
    '## 汇总',
    '',
    '| 股票 | 操作 | 数量 | 均价 | 成交额 |',
    '|---|---:|---:|---:|---:|',
  ]
  entries.filter((e) => e.symbol).forEach((entry) => {
    lines.push(`| ${entry.symbol} | ${actionLabel[entry.action]} | ${entry.quantity || ''} | ${entry.price || ''} | ${amount(entry).toFixed(2)} |`)
  })
  lines.push('', '费用：保存时由后台按设置中的佣金率、最低佣金、印花税率、过户费率计算并写入。')
  lines.push('', '## 持仓确认', '')
  overrides.forEach((override) => {
    lines.push(`- ${override.symbol}: 最终 ${override.final_quantity} 股，成本价 ${override.final_avg_cost}`)
  })
  if (notes) lines.push('', '## 备注', '', notes)
  return lines.join('\n')
}

function FieldLabel({ children }: { children: string }) {
  return <div style={{ marginBottom: 4, fontSize: 12, color: 'var(--text-secondary)' }}>{children}</div>
}

export default function DailyTradeLogPage() {
  const navigate = useNavigate()
  const { holdings, setHoldings } = usePortfolioStore()
  const [tradeDate, setTradeDate] = useState(today())
  const [entries, setEntries] = useState<DailyTradeEntry[]>([newEntry()])
  const [overrides, setOverrides] = useState<PositionOverride[]>([])
  const [notes, setNotes] = useState('')
  const [searchText, setSearchText] = useState('')

  const { data: holdingsData } = useQuery({
    queryKey: ['holdings'],
    queryFn: async () => {
      const resp = await portfolioApi.list()
      return resp.data as HoldingDetail[]
    },
  })

  useEffect(() => {
    if (holdingsData) setHoldings(holdingsData)
  }, [holdingsData, setHoldings])

  const symbols = useMemo(() => Array.from(new Set(entries.map((e) => e.symbol.trim()).filter(Boolean))), [entries])
  const preview = useMemo(() => buildPreview(tradeDate, entries, overrides, notes), [tradeDate, entries, overrides, notes])

  const holdingOptions = holdings.map((h) => ({
    label: `${h.holding.symbol} - ${h.holding.name || h.holding.symbol}`,
    value: h.holding.symbol,
  }))

  const filteredOptions = searchText
    ? holdingOptions.filter((opt) => {
        const input = searchText.toLowerCase()
        const value = String(opt.value).toLowerCase()
        const label = String(opt.label).toLowerCase()
        return value.includes(input) || label.includes(input)
      })
    : holdingOptions

  const getHoldingName = (symbol: string) => (
    holdings.find((h) => h.holding.symbol === symbol)?.holding.name || ''
  )

  const saveMutation = useMutation({
    mutationFn: () => rawApi.saveTradeLog({
      trade_date: tradeDate,
      entries: entries.filter((e) => e.symbol.trim()),
      position_overrides: overrides,
      notes,
    }),
    onSuccess: (resp) => {
      Message.success('每日操作已保存，持仓已更新')
      navigate(`/knowledge/raw/${encodeURIComponent(resp.data.source.source_id)}`)
    },
    onError: (err: any) => Message.error(err?.response?.data?.detail || '保存失败'),
  })

  const patchEntry = (index: number, patch: Partial<DailyTradeEntry>) => {
    setEntries((prev) => prev.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  }

  const syncOverrides = () => {
    setOverrides((prev) => {
      const bySymbol = new Map(prev.map((item) => [item.symbol, item]))
      return symbols.map((symbol) => bySymbol.get(symbol) || {
        symbol,
        final_quantity: 0,
        final_avg_cost: 0,
        final_current_price: null,
        override_reason: '',
      })
    })
  }

  const handleSave = () => {
    const validEntries = entries.filter((e) => e.symbol.trim())
    if (!tradeDate) {
      Message.warning('日期不能为空')
      return
    }
    if (validEntries.length === 0) {
      Message.warning('至少录入一条操作')
      return
    }
    for (const entry of validEntries) {
      if (['buy', 'sell', 'add', 'reduce', 'clear'].includes(entry.action)) {
        if (!entry.quantity || entry.quantity <= 0) {
          Message.warning(`${entry.symbol} 数量必须大于 0`)
          return
        }
        if (!entry.price || entry.price <= 0) {
          Message.warning(`${entry.symbol} 价格必须大于 0`)
          return
        }
      }
    }
    const missingOverrides = validEntries.some((entry) => !overrides.find((o) => o.symbol === entry.symbol))
    if (missingOverrides) {
      Message.warning('请先生成持仓确认')
      return
    }
    saveMutation.mutate()
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 className="page-header-title">每日操作</h2>
        <Button type="primary" icon={<IconSave />} loading={saveMutation.isPending} onClick={handleSave}>保存</Button>
      </div>

      <div className="page-grid-two-col-split">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <Card title="操作明细">
            <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <Input value={tradeDate} onChange={setTradeDate} placeholder="YYYY-MM-DD" style={{ width: 160 }} />
              <Button icon={<IconPlus />} onClick={() => setEntries((prev) => [...prev, newEntry()])}>添加一行</Button>
              <Button type="secondary" onClick={syncOverrides}>生成持仓确认</Button>
              <Tag color="arcoblue">交易费用由后台按设置自动计算</Tag>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {entries.map((entry, index) => (
                <div key={index} style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 12, background: 'rgba(245,241,235,0.02)' }}>
                  <div className="trade-entry-row">
                    <div>
                      <FieldLabel>股票</FieldLabel>
                      <Select
                        showSearch
                        allowClear
                        placeholder="输入代码或名称筛选"
                        filterOption={false}
                        options={filteredOptions}
                        value={entry.symbol || undefined}
                        onSearch={setSearchText}
                        onChange={(symbol) => {
                          const nextSymbol = symbol || ''
                          patchEntry(index, {
                            symbol: nextSymbol,
                            name: nextSymbol ? getHoldingName(nextSymbol) : '',
                          })
                        }}
                      />
                    </div>
                    <div>
                      <FieldLabel>操作</FieldLabel>
                      <Select value={entry.action} onChange={(v) => patchEntry(index, { action: v })} options={actionOptions} />
                    </div>
                    <div>
                      <FieldLabel>数量</FieldLabel>
                      <Input type="number" placeholder="股数" value={String(entry.quantity ?? '')} onChange={(v) => patchEntry(index, { quantity: Number(v || 0) })} />
                    </div>
                    <div>
                      <FieldLabel>成交价</FieldLabel>
                      <Input type="number" placeholder="价格" value={String(entry.price ?? '')} onChange={(v) => patchEntry(index, { price: Number(v || 0) })} />
                    </div>
                    <Tag color="arcoblue">成交额 {amount(entry).toFixed(2)}</Tag>
                    <Button type="text" status="danger" icon={<IconDelete />} onClick={() => setEntries((prev) => prev.filter((_, i) => i !== index))} />
                  </div>
                  <div className="trade-notes-row">
                    <TextArea placeholder="操作理由" value={entry.reason} onChange={(v) => patchEntry(index, { reason: v })} rows={2} />
                    <Input placeholder="关联分析 run_id（可选）" value={entry.linked_analysis_run_id} onChange={(v) => patchEntry(index, { linked_analysis_run_id: v })} />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card title="持仓确认">
            {overrides.length === 0 ? (
              <div style={{ color: 'var(--text-muted)' }}>录入股票后点击“生成持仓确认”。这里用于对照券商最终持仓，必要时修正系统计算结果。</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {overrides.map((override, index) => (
                  <div key={override.symbol} className="trade-override-row">
                    <Tag>{override.symbol}</Tag>
                    <div>
                      <FieldLabel>最终数量</FieldLabel>
                      <Input type="number" placeholder="券商显示股数" value={String(override.final_quantity)} onChange={(v) => setOverrides((prev) => prev.map((o, i) => i === index ? { ...o, final_quantity: Number(v || 0) } : o))} />
                    </div>
                    <div>
                      <FieldLabel>最终成本价</FieldLabel>
                      <Input type="number" placeholder="券商成本价" value={String(override.final_avg_cost)} onChange={(v) => setOverrides((prev) => prev.map((o, i) => i === index ? { ...o, final_avg_cost: Number(v || 0) } : o))} />
                    </div>
                    <div>
                      <FieldLabel>当前价</FieldLabel>
                      <Input type="number" placeholder="可选" value={String(override.final_current_price ?? '')} onChange={(v) => setOverrides((prev) => prev.map((o, i) => i === index ? { ...o, final_current_price: v ? Number(v) : null } : o))} />
                    </div>
                    <Input placeholder="校正原因（可选）" value={override.override_reason} onChange={(v) => setOverrides((prev) => prev.map((o, i) => i === index ? { ...o, override_reason: v } : o))} />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <Card title="Markdown 预览">
          <TextArea placeholder="备注" value={notes} onChange={setNotes} rows={4} style={{ marginBottom: 14 }} />
          <div className="report-content" style={{ minHeight: 520, maxHeight: 'calc(100vh - 260px)', overflow: 'auto', padding: 18, border: '1px solid var(--border-subtle)', borderRadius: 8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{preview}</ReactMarkdown>
          </div>
        </Card>
      </div>
    </div>
  )
}
