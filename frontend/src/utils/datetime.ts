export function parseApiDate(value: string): Date {
  const normalized = value.trim()

  // 后端当前返回的 MySQL/SQLAlchemy datetime 是无时区 ISO：
  // 2026-08-07T09:15:00
  // 数据库实际按 UTC 保存；若浏览器直接 new Date(value)，
  // Chrome 会把它当成本地时间，UTC+8 环境就会产生 8 小时偏差。
  //
  // 已经自带 Z 或 +08:00 等 offset 的值保持原样。
  const hasTimezone =
    /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized)

  return new Date(
    hasTimezone ? normalized : `${normalized}Z`,
  )
}

export function relativeApiTime(
  value: string | null,
  nowMs = Date.now(),
): string {
  if (!value) {
    return '暂无消息'
  }

  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }

  const diff = Math.max(0, nowMs - date.getTime())
  const minutes = Math.floor(diff / 60000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`

  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
  })
}
