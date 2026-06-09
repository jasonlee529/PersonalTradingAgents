import { Card, Tag, Progress } from '@arco-design/web-react'

interface DirectionCardProps {
  name: string
  rank: number
  totalScore: number
  fundScore: number
  policyScore: number
  sentimentScore: number
  selectionReason: string
  isSelected?: boolean
  onClick?: () => void
}

export default function DirectionCard({
  name,
  rank,
  totalScore,
  fundScore,
  policyScore,
  sentimentScore,
  selectionReason,
  isSelected = false,
  onClick,
}: DirectionCardProps) {
  const rankColors = [
    '#ff7d00',
    '#86909c',
    '#c57c5c',
    '#f2f3f5',
  ]
  const rankBg = rank <= 4 ? rankColors[rank - 1] || '#f2f3f5' : '#f2f3f5'
  const rankTextColor = rank <= 3 ? '#fff' : '#86909c'

  return (
    <Card
      className={`direction-card ${isSelected ? 'direction-card-selected' : ''}`}
      onClick={onClick}
      style={{ cursor: 'pointer', marginBottom: 12 }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: rankBg,
            color: rankTextColor,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 600,
            fontSize: 14,
          }}>
            {rank}
          </span>
          <span style={{ fontWeight: 600, fontSize: 16 }}>{name}</span>
        </div>
        <Tag color={totalScore >= 8 ? 'red' : totalScore >= 6 ? 'orange' : 'green'}>
          {totalScore.toFixed(1)}/10
        </Tag>
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>综合评分</div>
        <Progress
          percent={totalScore * 10}
          color={totalScore >= 8 ? '#ff7d00' : totalScore >= 6 ? '#ffb800' : '#00b42a'}
          showText={false}
          style={{ marginBottom: 8 }}
        />
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Tag size="small" color="arcoblue">资金 {fundScore.toFixed(1)}</Tag>
        <Tag size="small" color="blue">政策 {policyScore.toFixed(1)}</Tag>
        <Tag size="small" color="purple">情绪 {sentimentScore.toFixed(1)}</Tag>
      </div>

      {selectionReason && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-dim)' }}>
          {selectionReason}
        </div>
      )}
    </Card>
  )
}
