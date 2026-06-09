import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button, Card, Descriptions, Message, Spin, Tag, Tabs } from '@arco-design/web-react'
import { IconArrowLeft, IconCheckCircle } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import { wikiApi } from '../api/client'
import {
  labelForPageType,
  labelForTag,
  labelForWikiPageStatus,
  labelForWikiReviewStatus,
} from '../utils/displayLabels'

export default function WikiPageDetailPage() {
  const params = useParams()
  const navigate = useNavigate()
  const pageId = params.pageId ? decodeURIComponent(params.pageId) : ''

  const { data, isLoading } = useQuery({
    queryKey: ['wiki-page', pageId],
    queryFn: async () => {
      const resp = await wikiApi.detail(pageId)
      return resp.data as any
    },
    enabled: !!pageId,
  })

  const verifyMutation = useMutation({
    mutationFn: () => wikiApi.verify(pageId),
    onSuccess: () => Message.success('Hash 校验通过'),
    onError: (err: any) => Message.error(err?.response?.data?.detail || 'Hash 校验失败'),
  })

  if (isLoading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: 360 }}>
        <Spin size={36} />
      </div>
    )
  }

  if (!data) {
    return (
      <Card>
        <Button icon={<IconArrowLeft />} onClick={() => navigate('/wiki')}>返回</Button>
        <div style={{ padding: 40, color: 'var(--text-muted)' }}>页面不存在</div>
      </Card>
    )
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div style={{ minWidth: 0 }}>
          <Button type="text" icon={<IconArrowLeft />} onClick={() => navigate('/wiki')} style={{ marginBottom: 8 }}>
            返回知识库
          </Button>
          <h2 className="page-header-title" style={{ margin: 0 }}>{data.title}</h2>
        </div>
        <Button icon={<IconCheckCircle />} loading={verifyMutation.isPending} onClick={() => verifyMutation.mutate()}>
          校验 Hash
        </Button>
      </div>

      <Tabs defaultActiveTab="content">
        <Tabs.TabPane key="content" title="正文">
          <Card>
            <div className="report-content" style={{ padding: 18 }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.markdown || ''}</ReactMarkdown>
            </div>
          </Card>
        </Tabs.TabPane>
        <Tabs.TabPane key="meta" title="元数据">
          <Card className="metadata-card">
            <Descriptions
              column={1}
              border
              size="medium"
              data={[
                { label: '页面ID', value: <span style={{ fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>{data.page_id}</span> },
                { label: '页面类型', value: labelForPageType(data.page_type) },
                { label: '链接标识', value: data.slug },
                { label: '股票代码', value: data.symbol || '-' },
                { label: '主题', value: data.topic || '-' },
                { label: '交易日', value: data.trade_date || '-' },
                { label: '状态', value: labelForWikiPageStatus(data.status) },
                { label: '审核状态', value: labelForWikiReviewStatus(data.review_status) },
                { label: '版本', value: data.revision },
                { label: '创建时间', value: data.created_at },
                { label: '更新时间', value: data.updated_at },
              ]}
            />
            <div style={{ marginTop: 16 }}>
              <div style={{ marginBottom: 8 }}>标签:</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(data.tags || []).map((tag: string) => <Tag key={tag} title={tag}>{labelForTag(tag)}</Tag>)}
              </div>
            </div>
            <div style={{ marginTop: 16 }}>
              <div style={{ marginBottom: 8 }}>来源 ID:</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(data.source_ids || []).map((sid: string) => (
                  <Tag key={sid} color="arcoblue" style={{ cursor: 'pointer' }} onClick={() => navigate(`/knowledge/raw/${encodeURIComponent(sid)}`)}>
                    {sid}
                  </Tag>
                ))}
              </div>
            </div>
          </Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  )
}
