import { Space, Tooltip } from '@arco-design/web-react'

interface ValidationData {
  status: 'strong' | 'moderate' | 'weak' | 'missing'
  score: number
  evidence: string
}

interface ValidationBadgeProps {
  fund: ValidationData
  policy: ValidationData
  sentiment: ValidationData
}

const statusConfig = {
  strong: { color: '#00b42a', text: '强' },
  moderate: { color: '#ffb800', text: '中' },
  weak: { color: '#f53f3f', text: '弱' },
  missing: { color: '#86909c', text: '无' },
}

export default function ValidationBadge({ fund, policy, sentiment }: ValidationBadgeProps) {
  const items = [
    { key: '资金', data: fund },
    { key: '政策', data: policy },
    { key: '情绪', data: sentiment },
  ]

  return (
    <Space size="large">
      {items.map(({ key, data }) => {
        const config = statusConfig[data.status]
        return (
          <Tooltip key={key} content={`${key}: ${data.evidence} (评分 ${data.score})`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13 }}>{key}</span>
              <span
                style={{
                  backgroundColor: config.color,
                  color: '#fff',
                  fontSize: 11,
                  padding: '0 6px',
                  borderRadius: 4,
                  fontWeight: 500,
                }}
              >
                {config.text}
              </span>
            </div>
          </Tooltip>
        )
      })}
    </Space>
  )
}
