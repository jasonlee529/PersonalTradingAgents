import { Timeline, Tag } from '@arco-design/web-react'

interface CatalystEvent {
  event_name: string
  expected_date: string | null
  time_category: 'past' | 'imminent' | 'expected' | 'long_term'
  market_priced_in: number
  impact_assessment: string
  data_to_watch: string
}

interface CatalystTimelineProps {
  events: CatalystEvent[]
  next_key_event: string
}

const categoryConfig = {
  past: { label: '已发生', color: 'gray' },
  imminent: { label: '1周内', color: 'red' },
  expected: { label: '1月内', color: 'orange' },
  long_term: { label: '远期', color: 'blue' },
}

export default function CatalystTimeline({ events, next_key_event }: CatalystTimelineProps) {
  return (
    <div>
      {next_key_event && (
        <div style={{
          padding: '8px 12px',
          background: '#fff7e6',
          borderRadius: 4,
          marginBottom: 12,
          fontSize: 13,
        }}>
          <strong>下一关键事件:</strong> {next_key_event}
        </div>
      )}

      <Timeline>
        {events.map((event, index) => {
          const config = categoryConfig[event.time_category]
          return (
            <Timeline.Item
              key={index}
              label={event.expected_date || '待定'}
            >
              <div style={{ marginBottom: 4 }}>
                <span style={{ fontWeight: 500 }}>{event.event_name}</span>
                <Tag size="small" color={config.color} style={{ marginLeft: 8 }}>
                  {config.label}
                </Tag>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>
                {event.impact_assessment}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                市场定价: {event.market_priced_in}/10
                {event.data_to_watch && ` | 盯: ${event.data_to_watch}`}
              </div>
            </Timeline.Item>
          )
        })}
      </Timeline>
    </div>
  )
}
