import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { Button, Progress } from '@arco-design/web-react'
import {
  IconClose,
  IconMinus,
  IconThumbUp,
  IconThumbDown,
} from '@arco-design/web-react/icon'

export interface AnalysisStep {
  step_id: string
  label: string
  role: string
  character: string
  status: 'pending' | 'running' | 'done' | 'error'
  started_at?: string
  completed_at?: string
  detail?: string
}

interface AnalysisOverlayProps {
  visible: boolean
  steps: AnalysisStep[]
  phase: string
  status: string
  progress: string
  onClose: () => void
  onFeedback?: (stepId: string, type: 'upvote' | 'downvote') => void
  userFeedbacks?: Record<string, 'upvote' | 'downvote'>
  autoCloseDelay?: number
}

const statusConfig: Record<string, { icon: string; color: string }> = {
  pending: { icon: '○', color: 'var(--text-dim)' },
  running: { icon: '●', color: 'var(--accent)' },
  done: { icon: '✓', color: 'var(--color-down)' },
  error: { icon: '✗', color: 'var(--color-up)' },
}

export default function AnalysisOverlay({
  visible,
  steps,
  phase,
  status,
  progress,
  onClose,
  onFeedback,
  userFeedbacks = {},
  autoCloseDelay = 3000,
}: AnalysisOverlayProps) {
  const [minimized, setMinimized] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const clearAutoClose = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setCountdown(0)
  }, [])

  // Auto-close timer when analysis completes
  useEffect(() => {
    if (status === 'completed' && visible && autoCloseDelay > 0) {
      setCountdown(Math.ceil(autoCloseDelay / 1000))

      intervalRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (intervalRef.current) clearInterval(intervalRef.current)
            return 0
          }
          return prev - 1
        })
      }, 1000)

      timerRef.current = setTimeout(() => {
        onClose()
      }, autoCloseDelay)

      return () => {
        clearAutoClose()
      }
    }
  }, [status, visible, autoCloseDelay, onClose, clearAutoClose])

  const activeStep = useMemo(
    () => steps.find((s) => s.status === 'running') || steps.find((s) => s.step_id === phase),
    [steps, phase]
  )

  const doneCount = useMemo(() => steps.filter((s) => s.status === 'done').length, [steps])
  const percent = steps.length > 0 ? Math.round((doneCount / steps.length) * 100) : 0

  if (!visible) return null

  if (minimized) {
    return (
      <div className="analysis-minimized" onClick={() => { clearAutoClose(); setMinimized(false) }}>
        <span className="analysis-minimized-emoji">{activeStep?.character || '🤖'}</span>
        <span className="analysis-minimized-text">{percent}%</span>
      </div>
    )
  }

  const isCompleted = status === 'completed' || status === 'error'

  const handleClose = () => {
    clearAutoClose()
    onClose()
  }

  const handleMinimize = () => {
    clearAutoClose()
    setMinimized(true)
  }

  const handleFeedbackWrapper = (stepId: string, type: 'upvote' | 'downvote') => {
    clearAutoClose()
    onFeedback?.(stepId, type)
  }

  return (
    <div className="analysis-overlay">
      <div className="analysis-overlay-backdrop" onClick={handleClose} />
      <div className="analysis-overlay-content">
        <CelebrationStars active={status === 'completed'} />
        {/* Header */}
        <div className="analysis-overlay-header">
          <span className="analysis-overlay-title">
            {isCompleted ? '分析完成' : 'AI 分析进行中'}
            {countdown > 0 && (
              <span className="analysis-overlay-countdown">（{countdown}秒后关闭）</span>
            )}
          </span>
          <div className="analysis-overlay-controls">
            {!isCompleted && (
              <Button type="text" size="small" onClick={handleMinimize}>
                <IconMinus />
              </Button>
            )}
            <Button type="text" size="small" onClick={handleClose}>
              <IconClose />
            </Button>
          </div>
        </div>

        {/* Character Stage */}
        <div className="analysis-character-stage">
          <div
            className={`analysis-character-emoji ${
              status === 'running'
                ? 'character-float'
                : status === 'completed'
                  ? 'character-celebrate'
                  : activeStep?.status === 'running'
                    ? 'analysis-character-bounce'
                    : ''
            }`}
          >
            {status === 'error' ? '😢' : status === 'completed' ? '🎉' : activeStep?.character || '🤖'}
          </div>
          <div className="analysis-character-role">
            {status === 'error' ? '分析出错' : activeStep?.role || '准备中'}
          </div>
          <div className="analysis-character-label">
            {status === 'error' ? '' : activeStep?.label || ''}
          </div>
          <div className="analysis-character-detail">
            {status === 'error' ? progress || '未知错误' : progress || ''}
          </div>
        </div>

        {/* Progress Bar */}
        <div className={`analysis-progress-section ${status === 'running' ? 'progress-shimmer progress-pulse' : ''}`}>
          <Progress
            percent={percent}
            color={status === 'error' ? 'var(--color-up)' : 'var(--accent)'}
          />
        </div>

        {/* Timeline */}
        <div className="analysis-timeline">
          {steps.map((step) => (
            <TimelineItem
              key={step.step_id}
              step={step}
              isActive={step.step_id === phase}
              onFeedback={handleFeedbackWrapper}
              userFeedback={userFeedbacks[step.step_id]}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function TimelineItem({
  step,
  isActive,
  onFeedback,
  userFeedback,
}: {
  step: AnalysisStep
  isActive: boolean
  onFeedback?: (stepId: string, type: 'upvote' | 'downvote') => void
  userFeedback?: 'upvote' | 'downvote'
}) {
  const cfg = statusConfig[step.status] || statusConfig.pending

  return (
    <div
      className={`analysis-timeline-item ${isActive ? 'analysis-timeline-item-active' : ''}`}
    >
      <span className="analysis-timeline-character">{step.character}</span>
      <span className="analysis-timeline-role">{step.role}</span>
      <span className="analysis-timeline-label">{step.label}</span>
      <span className="analysis-timeline-status" style={{ color: cfg.color }}>
        {cfg.icon}
      </span>
      {step.status === 'done' && onFeedback && (
        <div className="analysis-timeline-feedback">
          <Button
            type="text"
            size="mini"
            className={userFeedback === 'upvote' ? 'feedback-active' : ''}
            onClick={() => onFeedback(step.step_id, 'upvote')}
          >
            <IconThumbUp />
          </Button>
          <Button
            type="text"
            size="mini"
            className={userFeedback === 'downvote' ? 'feedback-active' : ''}
            onClick={() => onFeedback(step.step_id, 'downvote')}
          >
            <IconThumbDown />
          </Button>
        </div>
      )}
    </div>
  )
}

function CelebrationStars({ active }: { active: boolean }) {
  const [stars, setStars] = useState<Array<{ id: number; x: number; y: number; emoji: string; delay: number }>>([])

  useEffect(() => {
    if (!active) {
      setStars([])
      return
    }
    const emojis = ['⭐', '✨', '🌟', '💫']
    const newStars = Array.from({ length: 12 }, (_, i) => ({
      id: i,
      x: 20 + Math.random() * 60,
      y: 20 + Math.random() * 40,
      emoji: emojis[Math.floor(Math.random() * emojis.length)],
      delay: Math.random() * 0.5,
    }))
    setStars(newStars)
    const timer = setTimeout(() => setStars([]), 2000)
    return () => clearTimeout(timer)
  }, [active])

  if (stars.length === 0) return null

  return (
    <div className="celebration-container" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      {stars.map((star) => (
        <span
          key={star.id}
          className="celebration-star"
          style={{
            left: `${star.x}%`,
            top: `${star.y}%`,
            animationDelay: `${star.delay}s`,
          }}
        >
          {star.emoji}
        </span>
      ))}
    </div>
  )
}
