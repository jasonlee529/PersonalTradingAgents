import { Tag, Space } from '@arco-design/web-react'

interface RiskTrigger {
  condition: string
  metric_name: string
  threshold: string
  severity: string
}

interface RiskPanelProps {
  overall_risk_level: string
  market_risks: RiskTrigger[]
  policy_risks: RiskTrigger[]
  fundamental_risks: RiskTrigger[]
  invalidation_conditions: string[]
  alternative_directions: string[]
}

const riskLevelConfig: Record<string, { color: string; label: string }> = {
  low: { color: '#00b42a', label: '低风险' },
  moderate: { color: '#ffb800', label: '中等风险' },
  high: { color: '#f53f3f', label: '高风险' },
}

const severityConfig: Record<string, string> = {
  warning: 'orange',
  critical: 'red',
}

export default function RiskPanel({
  overall_risk_level,
  market_risks,
  policy_risks,
  fundamental_risks,
  invalidation_conditions,
  alternative_directions,
}: RiskPanelProps) {
  const level = riskLevelConfig[overall_risk_level] || riskLevelConfig.moderate
  const allRisks = [
    ...market_risks.map((r) => ({ ...r, category: '市场' })),
    ...policy_risks.map((r) => ({ ...r, category: '政策' })),
    ...fundamental_risks.map((r) => ({ ...r, category: '基本面' })),
  ]

  return (
    <div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        marginBottom: 16,
        padding: '8px 12px',
        background: `${level.color}10`,
        borderRadius: 4,
        border: `1px solid ${level.color}30`,
      }}>
        <span style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: level.color,
          display: 'inline-block',
        }} />
        <span style={{ fontWeight: 600, fontSize: 14, color: level.color }}>
          {level.label}
        </span>
      </div>

      {allRisks.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
            风险触发器
          </div>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            {allRisks.map((risk, idx) => (
              <div
                key={idx}
                style={{
                  padding: '6px 10px',
                  borderRadius: 4,
                  background: risk.severity === 'critical' ? '#fff2f0' : 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                  <Tag size="small" color={severityConfig[risk.severity] || 'gray'}>
                    {risk.severity === 'critical' ? '严重' : '警告'}
                  </Tag>
                  <span style={{ fontWeight: 500 }}>{risk.condition}</span>
                </div>
                <div style={{ color: 'var(--text-dim)', paddingLeft: 4 }}>
                  指标: {risk.metric_name} | 阈值: {risk.threshold}
                </div>
              </div>
            ))}
          </Space>
        </div>
      )}

      {invalidation_conditions.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
            失效条件
          </div>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            {invalidation_conditions.map((cond, idx) => (
              <div
                key={idx}
                style={{
                  padding: '6px 10px',
                  borderRadius: 4,
                  background: '#fff2f0',
                  border: '1px solid #ffccc7',
                  fontSize: 12,
                  color: '#f53f3f',
                }}
              >
                {cond}
              </div>
            ))}
          </Space>
        </div>
      )}

      {alternative_directions.length > 0 && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
            替代方向
          </div>
          <Space size="small">
            {alternative_directions.map((alt, idx) => (
              <Tag key={idx} color="arcoblue">{alt}</Tag>
            ))}
          </Space>
        </div>
      )}
    </div>
  )
}
