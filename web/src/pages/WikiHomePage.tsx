import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Spin, Tag, Statistic, Grid, Input, Tooltip } from '@arco-design/web-react'
import { IconRefresh, IconStorage, IconCheckCircle, IconList, IconFile, IconPlus } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import { wikiApi } from '../api/client'
import { labelForPageType, labelForWikiIngestStatus, labelForWikiTriggerType } from '../utils/displayLabels'

export default function WikiHomePage() {
  const navigate = useNavigate()
  const [searchQ, setSearchQ] = useState('')

  const { data: pages, isLoading: pagesLoading } = useQuery({
    queryKey: ['wiki-pages', searchQ],
    queryFn: async () => {
      const resp = await wikiApi.pages({ limit: 200, q: searchQ || undefined })
      return resp.data as any[]
    },
  })

  const { data: pendingSources } = useQuery({
    queryKey: ['wiki-pending-sources'],
    queryFn: async () => {
      const resp = await wikiApi.pendingSources({ limit: 100 })
      return resp.data as any[]
    },
  })

  const { data: ingestRuns } = useQuery({
    queryKey: ['wiki-ingest-runs'],
    queryFn: async () => {
      const resp = await wikiApi.ingestRuns({ limit: 10 })
      return resp.data as any[]
    },
  })

  const { data: indexContent } = useQuery({
    queryKey: ['wiki-index'],
    queryFn: async () => {
      try {
        const resp = await wikiApi.content('home:index')
        return resp.data.content as string
      } catch {
        return ''
      }
    },
  })

  const rebuildMutation = useMutation({
    mutationFn: () => wikiApi.rebuildIndex(),
  })

  if (pagesLoading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: 360 }}>
        <Spin size={36} />
      </div>
    )
  }

  const recentPages = (pages || [])
    .filter((p) => p.page_type !== 'home' && p.page_type !== 'log')
    .sort((a: any, b: any) => (b.updated_at || '').localeCompare(a.updated_at || ''))
    .slice(0, 10)

  const ingestStatusColor = (status: string) => {
    if (status === 'completed') return 'green'
    if (status === 'failed') return 'red'
    if (status === 'cancelled') return 'gray'
    return 'orange'
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 className="page-header-title" style={{ margin: 0 }}>知识库</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            placeholder="搜索页面..."
            value={searchQ}
            onChange={(v) => setSearchQ(v)}
            onPressEnter={() => {}}
            style={{ width: 140 }}
          />
          <Button icon={<IconStorage />} onClick={() => navigate('/wiki/ingest')}>
            写入队列
          </Button>
          <Button icon={<IconCheckCircle />} onClick={() => navigate('/wiki/lint')}>
            健康检查
          </Button>
          <Button icon={<IconList />} onClick={() => navigate('/wiki/claims')}>
            论断
          </Button>
          <Tooltip content="重新生成知识库首页目录，汇总所有页面、待处理来源和活跃论断。写入完成后会自动执行；手动点击用于强制刷新。">
            <Button icon={<IconRefresh />} loading={rebuildMutation.isPending} onClick={() => rebuildMutation.mutate()}>
              重建索引
            </Button>
          </Tooltip>
        </div>
      </div>

      <Grid.Row gutter={[20, 20]}>
        <Grid.Col span={16}>
          <Card title="索引">
            {indexContent ? (
              <div className="report-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{indexContent}</ReactMarkdown>
              </div>
            ) : (
              <div style={{ color: 'var(--text-muted)' }}>索引为空</div>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={8}>
          <Card style={{ marginBottom: 16, borderColor: 'var(--border-accent)' }}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <div style={{ width: 42, height: 42, borderRadius: 10, display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent)', border: '1px solid var(--border-accent)', flexShrink: 0 }}>
                <IconStorage style={{ fontSize: 21 }} />
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ color: 'var(--text-primary)', fontSize: 16, fontWeight: 700 }}>原始材料</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7, marginTop: 6 }}>
                  查看导入知识库前的公告、新闻、研报、分析输出和手动材料。
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
                  <Button type="primary" icon={<IconFile />} onClick={() => navigate('/knowledge/raw')}>查看原始材料</Button>
                  <Button type="primary" icon={<IconPlus />} onClick={() => navigate('/knowledge/raw/new')}>新增材料</Button>
                </div>
              </div>
            </div>
          </Card>

          <Card title="统计">
            <div className="page-grid-two-col-equal">
              <Statistic title="总页面" value={(pages || []).filter((p: any) => p.page_type !== 'home' && p.page_type !== 'log').length} />
              <Statistic title="待处理" value={(pendingSources || []).length} />
            </div>
          </Card>

          <Card title="最近页面" style={{ marginTop: 16 }}>
            {(recentPages || []).map((p: any) => (
              <div
                key={p.page_id}
                style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}
                onClick={() => navigate(`/wiki/pages/${encodeURIComponent(p.page_id)}`)}
              >
                <div style={{ fontWeight: 500 }}>{p.title}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  <Tag size="small">{labelForPageType(p.page_type)}</Tag>
                  {p.updated_at?.slice(0, 10)}
                </div>
              </div>
            ))}
            {recentPages.length === 0 && <div style={{ color: 'var(--text-muted)' }}>暂无页面</div>}
          </Card>

          <Card title="最近写入" style={{ marginTop: 16 }}>
            {(ingestRuns || []).slice(0, 5).map((r: any) => (
              <div key={r.run_id} style={{ padding: '6px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: 13 }}>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <Tag size="small" title={r.trigger_type}>{labelForWikiTriggerType(r.trigger_type)}</Tag>
                  <Tag size="small" color={ingestStatusColor(r.status)} title={r.status}>{labelForWikiIngestStatus(r.status)}</Tag>
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>{r.started_at?.slice(0, 16)}</div>
              </div>
            ))}
            {(ingestRuns || []).length === 0 && <div style={{ color: 'var(--text-muted)' }}>暂无记录</div>}
          </Card>
        </Grid.Col>
      </Grid.Row>
    </div>
  )
}
