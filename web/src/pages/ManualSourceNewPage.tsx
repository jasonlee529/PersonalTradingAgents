import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Input, Message, Select, Tabs, Tag } from '@arco-design/web-react'
import { IconSave } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import { rawApi, portfolioApi } from '../api/client'
import { usePortfolioStore, type HoldingDetail } from '../store/usePortfolioStore'
import { labelForTag } from '../utils/displayLabels'

const TextArea = Input.TextArea
const TabPane = Tabs.TabPane

const subtypeOptions = [
  { label: '观点', value: 'opinion' },
  { label: '文章', value: 'article' },
  { label: '公告', value: 'announcement' },
  { label: '研报', value: 'research_report' },
  { label: '笔记', value: 'note' },
  { label: '其他', value: 'other' },
]

function splitCsv(value: string): string[] {
  return value.split(/[,，\s]+/).map((v) => v.trim()).filter(Boolean)
}

function validUrl(url: string): boolean {
  if (!url) return true
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

export default function ManualSourceNewPage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [manualSubtype, setManualSubtype] = useState('article')
  const [symbols, setSymbols] = useState<string[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [author, setAuthor] = useState('')
  const [publishedAt, setPublishedAt] = useState('')
  const [userComment, setUserComment] = useState('')
  const [tagsRaw, setTagsRaw] = useState('')
  const [searchText, setSearchText] = useState('')
  const { holdings, setHoldings } = usePortfolioStore()

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

  const holdingOptions = holdings.map((h) => ({
    label: `${h.holding.symbol} - ${h.holding.name}`,
    value: h.holding.symbol,
  }))

  const filteredOptions = searchText
    ? holdingOptions.filter((opt) => {
        const input = searchText.toLowerCase()
        const val = String(opt.value).toLowerCase()
        const label = String(opt.label).toLowerCase()
        return val.includes(input) || label.includes(input)
      })
    : holdingOptions

  const tags = useMemo(() => {
    const base = [`manual/${manualSubtype}`]
    return Array.from(new Set([...base, ...symbols.map((s) => `stock/${s}`), ...splitCsv(tagsRaw)]))
  }, [manualSubtype, symbols, tagsRaw])

  const saveMutation = useMutation({
    mutationFn: () => rawApi.create({
      source_kind: 'manual_source',
      origin: 'user',
      title,
      markdown,
      metadata: {
        manual_subtype: manualSubtype,
        symbols,
        source_url: sourceUrl,
        author,
        published_at: publishedAt,
        user_comment: userComment,
        tags,
      },
    }),
    onSuccess: (resp) => {
      const data = resp.data
      if (data.duplicate) {
        Message.info('该材料已存在，已打开已有 source')
      } else {
        Message.success('材料已保存到 raw')
      }
      navigate(`/knowledge/raw/${encodeURIComponent(data.source_id)}`)
    },
    onError: (err: any) => Message.error(err?.response?.data?.detail || '保存失败'),
  })

  const handleSave = () => {
    if (!title.trim()) {
      Message.warning('标题不能为空')
      return
    }
    if (!markdown.trim()) {
      Message.warning('Markdown 正文不能为空')
      return
    }
    if (!manualSubtype) {
      Message.warning('请选择子类型')
      return
    }
    if (!validUrl(sourceUrl)) {
      Message.warning('原文链接必须是 http/https URL')
      return
    }
    saveMutation.mutate()
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 className="page-header-title">新增手动材料</h2>
        <Button type="primary" icon={<IconSave />} loading={saveMutation.isPending} onClick={handleSave}>
          保存
        </Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '360px minmax(0, 1fr)', gap: 20, alignItems: 'start' }}>
        <Card title="材料信息">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Input placeholder="标题" value={title} onChange={setTitle} />
            <Select value={manualSubtype} onChange={setManualSubtype} options={subtypeOptions} />
            <Select
              mode="multiple"
              showSearch
              allowClear
              placeholder="选择持仓股票"
              filterOption={false}
              options={filteredOptions}
              onSearch={setSearchText}
              value={symbols}
              onChange={setSymbols}
            />
            <Input placeholder="原文链接" value={sourceUrl} onChange={setSourceUrl} />
            <Input placeholder="作者" value={author} onChange={setAuthor} />
            <Input placeholder="发布时间，例如 2026-06-04" value={publishedAt} onChange={setPublishedAt} />
            <TextArea placeholder="用户备注" value={userComment} onChange={setUserComment} rows={4} />
            <Input placeholder="额外标签，逗号分隔" value={tagsRaw} onChange={setTagsRaw} />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {tags.map((tag) => <Tag key={tag} title={tag}>{labelForTag(tag)}</Tag>)}
            </div>
          </div>
        </Card>

        <Card title="正文">
          <Tabs defaultActiveTab="edit">
            <TabPane key="edit" title="编辑">
              <TextArea
                value={markdown}
                onChange={setMarkdown}
                placeholder="# 标题&#10;&#10;正文..."
                rows={22}
                style={{ fontFamily: 'var(--font-mono)', lineHeight: 1.7 }}
              />
            </TabPane>
            <TabPane key="preview" title="预览">
              <div className="report-content" style={{ minHeight: 420, padding: 18, border: '1px solid var(--border-subtle)', borderRadius: 8 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown || '*暂无预览*'}</ReactMarkdown>
              </div>
            </TabPane>
          </Tabs>
        </Card>
      </div>
    </div>
  )
}
