const dataDateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
})

const dataTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function parseDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T00:00:00`)
    : new Date(value)
}

export function formatDataDate(value?: string | null, fallback = '未提供') {
  if (!value) return fallback
  const parsed = parseDate(value)
  return Number.isNaN(parsed.getTime()) ? value : dataDateFormatter.format(parsed)
}

export function formatDataTime(value?: string | null, fallback = '未记录') {
  if (!value) return fallback
  const parsed = parseDate(value)
  return Number.isNaN(parsed.getTime()) ? value : dataTimeFormatter.format(parsed)
}

export function formatEvidenceTime(asOf: string, fetchedAt?: string) {
  return fetchedAt ? formatDataTime(fetchedAt) : formatDataDate(asOf)
}
