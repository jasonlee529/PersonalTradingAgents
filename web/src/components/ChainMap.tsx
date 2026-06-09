import { Tag, Space } from '@arco-design/web-react'

interface ChainSegment {
  segment_name: string
  position: string
  market_perception: string
  reality_assessment: string
  expectation_gap: number
  key_players: string[]
  investment_logic: string
}

interface ChainMapProps {
  segments: ChainSegment[]
  top_segment: string
  diffusion_path: string
}

const positionLabels: Record<string, string> = {
  upstream: '上游',
  midstream: '中游',
  downstream: '下游',
  supporting: '配套',
}

const positionColors: Record<string, string> = {
  upstream: 'red',
  midstream: 'orange',
  downstream: 'green',
  supporting: 'purple',
}

export default function ChainMap({ segments, top_segment, diffusion_path }: ChainMapProps) {
  const sorted = [...segments].sort((a, b) => b.expectation_gap - a.expectation_gap)

  return (
    <div>
      {diffusion_path && (
        <div style={{
          padding: '8px 12px',
          background: 'var(--bg-card)',
          borderRadius: 4,
          marginBottom: 12,
          fontSize: 13,
          border: '1px solid var(--border-subtle)',
        }}>
          <strong>扩散路径:</strong> {diffusion_path}
        </div>
      )}

      <Space direction="vertical" size="medium" style={{ width: '100%' }}>
        {sorted.map((seg, idx) => {
          const isTop = seg.segment_name === top_segment
          const pos = seg.position || 'upstream'
          return (
            <div
              key={idx}
              style={{
                padding: 12,
                borderRadius: 'var(--radius-md)',
                border: isTop ? '1px solid #165dff' : '1px solid var(--border-subtle)',
                background: isTop ? '#f0f3ff' : 'var(--bg-card)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Tag size="small" color={positionColors[pos] || 'gray'}>
                  {positionLabels[pos] || pos}
                </Tag>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{seg.segment_name}</span>
                {isTop && (
                  <Tag size="small" color="arcoblue">预期差最大</Tag>
                )}
              </div>

              {seg.investment_logic && (
                <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>
                  {seg.investment_logic}
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12 }}>
                <span>
                  预期差: <strong style={{ color: seg.expectation_gap >= 7 ? '#f53f3f' : '#165dff' }}>
                    {seg.expectation_gap.toFixed(1)}
                  </strong>/10
                </span>
                {seg.reality_assessment && (
                  <span style={{ color: 'var(--text-dim)' }}>实际: {seg.reality_assessment}</span>
                )}
              </div>
            </div>
          )
        })}
      </Space>
    </div>
  )
}
