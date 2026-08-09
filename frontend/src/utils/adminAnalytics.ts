import type { DailyQuestionPoint } from '@/types/admin'

export function formatPercent(value: number): string {
  return `${Math.round(value * 10) / 10}%`
}

export function buildLinePath(
  points: DailyQuestionPoint[],
  width: number,
  height: number,
  padding = 18,
): string {
  if (points.length === 0) {
    return ''
  }

  const max = Math.max(...points.map((item) => item.question_count), 1)
  const usableWidth = Math.max(width - padding * 2, 1)
  const usableHeight = Math.max(height - padding * 2, 1)

  return points
    .map((item, index) => {
      const x =
        points.length === 1
          ? width / 2
          : padding + (usableWidth * index) / (points.length - 1)
      const y =
        height -
        padding -
        (item.question_count / max) * usableHeight
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}
