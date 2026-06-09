import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Spin, Tag, Input, Select } from '@arco-design/web-react'
import { IconFile } from '@arco-design/web-react/icon'
import { useQuery } from '@tanstack/react-query'
import { wikiApi } from '../api/client'
import DataList from '../components/DataList'
import EmptyState from '../components/EmptyState'
import {
  claimStatusLabels,
  claimTypeLabels,
  labelForClaimStatus,
  labelForClaimType,
  labelForPolarity,
  labelForSubjectType,
  subjectTypeLabels,
} from '../utils/displayLabels'

interface Claim {
  claim_id: string
  subject_type: string
  subject_id: string
  claim_type: string
  statement: string
  polarity: string
  status: string
  confidence: number
  source_ids: string[]
  page_ids: string[]
  updated_at: string
}

export default function WikiClaimsPage() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState({
    subject_type: '',
    subject_id: '',
    claim_type: '',
    status: '',
  })

  const { data: claims, isLoading } = useQuery({
    queryKey: ['wiki-claims', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit: 200 }
      if (filters.subject_type) params.subject_type = filters.subject_type
      if (filters.subject_id) params.subject_id = filters.subject_id
      if (filters.claim_type) params.claim_type = filters.claim_type
      if (filters.status) params.status = filters.status
      const resp = await wikiApi.claims(params)
      return resp.data as Claim[]
    },
  })

  const statusColor = (s: string) => {
    if (s === 'active') return 'green'
    if (s === 'superseded') return 'blue'
    if (s === 'contradicted') return 'red'
    if (s === 'resolved') return 'purple'
    return 'gray'
  }

  const columns = [
    {
      title: '论断',
      render: (_: any, record: Claim) => (
        <div>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>{record.statement}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            <Tag size="small" color="blue" title={record.claim_type}>{labelForClaimType(record.claim_type)}</Tag>
            <Tag size="small" color={statusColor(record.status)} title={record.status}>{labelForClaimStatus(record.status)}</Tag>
            {record.polarity && <Tag size="small" title={record.polarity}>{labelForPolarity(record.polarity)}</Tag>}
          </div>
        </div>
      ),
    },
    {
      title: '主体',
      width: 120,
      render: (_: any, record: Claim) => (
        <div>
          <div>{labelForSubjectType(record.subject_type)}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{record.subject_id}</div>
        </div>
      ),
    },
    {
      title: '来源',
      width: 180,
      render: (_: any, record: Claim) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, justifyContent: 'center' }}>
          {(record.source_ids || []).slice(0, 3).map((sid) => (
            <Tag key={sid} size="small" title={sid} style={{ cursor: 'pointer', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} onClick={() => navigate(`/knowledge/raw/${encodeURIComponent(sid)}`)}>
              {sid}
            </Tag>
          ))}
          {(record.source_ids || []).length > 3 && (
            <Tag size="small">+{(record.source_ids || []).length - 3}</Tag>
          )}
        </div>
      ),
    },
    {
      title: '置信度',
      width: 80,
      dataIndex: 'confidence',
      render: (v: number) => (
        <Tag color={v >= 0.7 ? 'green' : v >= 0.4 ? 'orange' : 'red'}>
          {(v * 100).toFixed(0)}%
        </Tag>
      ),
    },
    {
      title: '页面',
      width: 140,
      render: (_: any, record: Claim) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, justifyContent: 'center' }}>
          {(record.page_ids || []).slice(0, 2).map((pid) => (
            <Tag
              key={pid}
              size="small"
              title={pid}
              style={{ cursor: 'pointer', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              onClick={() => navigate(`/wiki/pages/${encodeURIComponent(pid)}`)}
            >
              {pid}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: '更新时间',
      width: 160,
      dataIndex: 'updated_at',
      render: (v: string) => (
        <span style={{ whiteSpace: 'nowrap' }}>{v?.slice(0, 19).replace('T', ' ') || '-'}</span>
      ),
    },
  ]

  return (
    <div>
      <div
        className="page-header"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}
      >
        <h2 className="page-header-title" style={{ margin: 0 }}>论断注册表</h2>
        <Button icon={<IconFile />} onClick={() => navigate('/wiki')}>
          知识库首页
        </Button>
      </div>

      <Card style={{ marginBottom: 16 }} bodyStyle={{ padding: 0 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Select
            placeholder="主体类型"
            style={{ width: 140 }}
            value={filters.subject_type || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, subject_type: v || '' }))}
            allowClear
          >
            {Object.entries(subjectTypeLabels).filter(([value]) => value !== 'general').map(([value, label]) => (
              <Select.Option key={value} value={value}>{label}</Select.Option>
            ))}
          </Select>
          <Input
            placeholder="主体ID"
            style={{ width: 140 }}
            value={filters.subject_id}
            onChange={(v) => setFilters((f) => ({ ...f, subject_id: v }))}
          />
          <Select
            placeholder="论断类型"
            style={{ width: 140 }}
            value={filters.claim_type || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, claim_type: v || '' }))}
            allowClear
          >
            {Object.entries(claimTypeLabels).map(([value, label]) => (
              <Select.Option key={value} value={value}>{label}</Select.Option>
            ))}
          </Select>
          <Select
            placeholder="状态"
            style={{ width: 140 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v || '' }))}
            allowClear
          >
            {Object.entries(claimStatusLabels).map(([value, label]) => (
              <Select.Option key={value} value={value}>{label}</Select.Option>
            ))}
          </Select>
        </div>
      </Card>

      <Card>
        {isLoading ? (
          <div style={{ display: 'grid', placeItems: 'center', minHeight: 200 }}>
            <Spin size={36} />
          </div>
        ) : (claims || []).length === 0 ? (
          <EmptyState title="暂无论断" description="没有符合条件的论断记录。" />
        ) : (
          <DataList
            columns={columns}
            data={claims || []}
            rowKey="claim_id"
            loading={isLoading}
            pagination={{ pageSize: 20 }}
          />
        )}
      </Card>
    </div>
  )
}
