import { AlertCircle, CheckCircle2, CircleDashed, Database, Info } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { CheckState, DataFreshness, DataResolution, DataStatus } from '../types'

export const semanticBadgeClassName = {
  success: 'border-status-live/20 bg-status-live/10 text-status-live',
  warning: 'border-status-cached/20 bg-status-cached/10 text-status-cached',
  info: 'border-status-info/20 bg-status-info/10 text-status-info',
  muted: 'text-muted-foreground',
} as const

export function AIConnectionStatus({
  configured,
  status,
}: {
  configured: boolean
  status?: 'connected' | 'disconnected'
}) {
  if (configured && status === 'connected') {
    return <Badge variant="outline" className={semanticBadgeClassName.success}><CheckCircle2 data-icon="inline-start" />AI 已连接</Badge>
  }
  return <Badge variant="outline" className={semanticBadgeClassName.warning}><CircleDashed data-icon="inline-start" />AI 未连接</Badge>
}

export function sourceDisplayNames(source: string) {
  return source.split(/\s*[·,]\s*/).filter(Boolean)
}

export function evidenceSourceDisplayName(source?: string) {
  return source || '来源未记录'
}

const stateContent = {
  pass: { label: '通过', icon: CheckCircle2, variant: 'outline', className: semanticBadgeClassName.success },
  concern: { label: '关注', icon: Info, variant: 'outline', className: semanticBadgeClassName.warning },
  fail: { label: '不通过', icon: AlertCircle, variant: 'destructive', className: 'border-destructive/40' },
} as const

export function CheckStatus({ state }: { state: CheckState }) {
  const item = stateContent[state]
  const Icon = item.icon
  return <Badge variant={item.variant} className={item.className}><Icon data-icon="inline-start" />{item.label}</Badge>
}

export function SourceStatus({ status }: { status: DataStatus }) {
  const content = {
    pending: { label: '等待数据源', icon: CircleDashed, variant: 'outline', className: semanticBadgeClassName.muted },
    live: { label: '最新数据', icon: CheckCircle2, variant: 'outline', className: semanticBadgeClassName.success },
    historical: { label: '历史数据', icon: Database, variant: 'outline', className: semanticBadgeClassName.info },
    cached: { label: '缓存数据', icon: Database, variant: 'outline', className: semanticBadgeClassName.warning },
    demo: { label: '示例快照', icon: Info, variant: 'outline', className: semanticBadgeClassName.info },
    unavailable: { label: '数据源不可用', icon: AlertCircle, variant: 'destructive', className: 'border-destructive/40' },
  }[status] as { label: string; icon: typeof CircleDashed; variant: 'outline' | 'destructive'; className?: string }
  const Icon = content.icon
  return <Badge variant={content.variant} className={content.className}><Icon data-icon="inline-start" />{content.label}</Badge>
}

export function ProviderStatus({ status }: { status: 'available' | 'cached' | 'unavailable' }) {
  if (status === 'unavailable') {
    return <Badge variant="destructive" className="border-destructive/40"><AlertCircle data-icon="inline-start" />数据源不可用</Badge>
  }
  if (status === 'cached') {
    return <Badge variant="outline" className={semanticBadgeClassName.warning}><Database data-icon="inline-start" />使用缓存</Badge>
  }
  return <Badge variant="outline" className={semanticBadgeClassName.success}>
    <CheckCircle2 data-icon="inline-start" />数据源可用
  </Badge>
}

export function ResolutionStatus({ resolution }: { resolution?: DataResolution }) {
  if (resolution === 'conflict') {
    return <Badge variant="destructive" className="border-destructive/40"><AlertCircle data-icon="inline-start" />冲突退避</Badge>
  }
  if (resolution === 'fallback') {
    return <Badge variant="outline" className={semanticBadgeClassName.warning}><Database data-icon="inline-start" />备用源</Badge>
  }
  return null
}

export function FreshnessStatus({ freshness }: { freshness?: DataFreshness }) {
  if (!freshness) {
    return <Badge variant="outline" className={semanticBadgeClassName.muted}><Info data-icon="inline-start" />新鲜度未记录</Badge>
  }
  if (freshness === 'cached') {
    return <Badge variant="outline" className={semanticBadgeClassName.warning}><Database data-icon="inline-start" />缓存</Badge>
  }
  return <Badge variant="outline" className={semanticBadgeClassName.success}><CheckCircle2 data-icon="inline-start" />最新</Badge>
}

export const recommendationLabel = { follow: '关注', wait: '待观察', avoid: '回避' } as const

export const recommendationVariant = { follow: 'outline', wait: 'outline', avoid: 'destructive' } as const
export const recommendationClassName = {
  follow: semanticBadgeClassName.info,
  wait: semanticBadgeClassName.warning,
  avoid: 'border-destructive/40',
} as const
