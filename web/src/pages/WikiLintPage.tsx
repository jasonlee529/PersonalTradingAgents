import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Spin, Table, Tag, Message, Statistic } from '@arco-design/web-react'
import { IconRefresh, IconFile } from '@arco-design/web-react/icon'
import { useMutation, useQuery } from '@tanstack/react-query'
import { wikiApi } from '../api/client'
import { labelForLintIssueKind, labelForLintSeverity, labelForLintStatus } from '../utils/displayLabels'

interface LintIssue {
  severity: string
  kind: string
  page_id: string
  message: string
}

interface LintSummary {
  pages?: number
  broken_links?: number
  uncited_claims?: number
  pending_sources?: number
  orphan_pages?: number
  duplicate_claims?: number
  empty_pages?: number
  stale_pages?: number
  stale_contradictions?: number
}

interface LintResult {
  status: string
  checked_at: string
  issues: LintIssue[]
  summary: LintSummary
}

export default function WikiLintPage() {
  const navigate = useNavigate()
  const [lastRun, setLastRun] = useState<LintResult | null>(null)

  const { data: latestLint, isLoading } = useQuery({
    queryKey: ['wiki-lint-latest'],
    queryFn: async () => {
      try {
        const resp = await wikiApi.latestLint()
        return resp.data as LintResult
      } catch {
        return null
      }
    },
  })

  const lintMutation = useMutation({
    mutationFn: () => wikiApi.runLint(),
    onSuccess: (resp) => {
      const data = resp.data as LintResult
      setLastRun(data)
      Message.success(`检查完成: ${labelForLintStatus(data.status)}`)
    },
    onError: (err: any) => {
      Message.error(err?.response?.data?.detail || '检查失败')
    },
  })

  const displayResult = lastRun || latestLint

  const severityColor = (s: string) => {
    if (s === 'error') return 'red'
    if (s === 'warning') return 'orange'
    return 'blue'
  }

  const statusColor = (s: string) => {
    if (s === 'ok') return 'green'
    if (s === 'warning') return 'orange'
    return 'red'
  }

  const issueColumns = [
    {
      title: '级别',
      dataIndex: 'severity',
      width: 100,
      render: (v: string) => <Tag color={severityColor(v)} title={v}>{labelForLintSeverity(v)}</Tag>,
    },
    {
      title: '类型',
      dataIndex: 'kind',
      width: 140,
      render: (v: string) => <span title={v}>{labelForLintIssueKind(v)}</span>,
    },
    {
      title: '页面',
      dataIndex: 'page_id',
      width: 200,
      render: (v: string) => (
        <span
          style={{ cursor: 'pointer', color: 'var(--color-primary)' }}
          onClick={() => navigate(`/wiki/pages/${encodeURIComponent(v)}`)}
        >
          {v}
        </span>
      ),
    },
    {
      title: '描述',
      dataIndex: 'message',
    },
  ]

  return (
    <div>
      <div
        className="page-header"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}
      >
        <h2 className="page-header-title" style={{ margin: 0 }}>知识库健康检查</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<IconFile />} onClick={() => navigate('/wiki')}>
            知识库首页
          </Button>
          <Button
            type="primary"
            icon={<IconRefresh />}
            loading={lintMutation.isPending}
            onClick={() => lintMutation.mutate()}
          >
            运行检查
          </Button>
        </div>
      </div>

      {isLoading && !displayResult ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 200 }}>
          <Spin size={36} />
        </div>
      ) : displayResult ? (
        <>
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, paddingBottom: 12, borderBottom: '1px solid var(--color-border-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>状态</span>
                <Tag color={statusColor(displayResult.status)} size="small">
                  {labelForLintStatus(displayResult.status)}
                </Tag>
              </div>
              <div style={{ width: 1, height: 14, background: 'var(--color-border-2)' }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>检查时间</span>
                <span style={{ fontSize: 13, fontWeight: 500 }}>
                  {displayResult.checked_at?.slice(0, 19).replace('T', ' ')}
                </span>
              </div>
            </div>
            {displayResult.summary && (
              <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', paddingTop: 16 }}>
                <Statistic
                  title="页面总数"
                  value={displayResult.summary.pages || 0}
                />
                <Statistic
                  title="断链"
                  value={displayResult.summary.broken_links || 0}
                />
                <Statistic
                  title="未引用论断"
                  value={displayResult.summary.uncited_claims || 0}
                />
                <Statistic
                  title="待处理来源"
                  value={displayResult.summary.pending_sources || 0}
                />
                <Statistic
                  title="孤立页面"
                  value={displayResult.summary.orphan_pages || 0}
                />
                <Statistic
                  title="重复论断"
                  value={displayResult.summary.duplicate_claims || 0}
                />
                <Statistic
                  title="空页面"
                  value={displayResult.summary.empty_pages || 0}
                />
              </div>
            )}
          </Card>

          <Card title={`问题 (${displayResult.issues?.length || 0})`}>
            <Table
              columns={issueColumns}
              data={displayResult.issues || []}
              rowKey={(record: LintIssue) => `${record.kind}-${record.page_id}-${record.message.slice(0, 20)}`}
              pagination={{ pageSize: 20 }}
            />
          </Card>
        </>
      ) : (
        <Card>
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
            <div>暂无检查记录</div>
            <Button
              type="primary"
              icon={<IconRefresh />}
              style={{ marginTop: 16 }}
              loading={lintMutation.isPending}
              onClick={() => lintMutation.mutate()}
            >
              运行检查
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
