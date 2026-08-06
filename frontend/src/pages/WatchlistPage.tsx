import { FormEvent, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CircleAlert, Plus, Star, Trash2 } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { api } from '../api'
import type { WatchlistItem } from '../types'
import { EmptyState } from '../components/EmptyState'
import { useRowSelection } from '@/hooks/use-row-selection'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { contentOffset, reducedFadeTransition, spatialSpring } from '@/lib/motion'

const legacyKey = 'stockllm.watchlist'

function readLegacyWatchlist(): Array<Pick<WatchlistItem, 'code' | 'name' | 'note'>> {
  try {
    const value = localStorage.getItem(legacyKey)
    if (!value) return []
    const items = JSON.parse(value) as unknown
    if (!Array.isArray(items)) return []
    return items.filter((item): item is Pick<WatchlistItem, 'code' | 'name' | 'note'> => {
      if (!item || typeof item !== 'object') return false
      const candidate = item as Record<string, unknown>
      return /^\d{6}$/.test(String(candidate.code)) && typeof candidate.name === 'string' && typeof candidate.note === 'string'
    }).map((item) => ({ code: item.code, name: item.name, note: item.note }))
  } catch {
    return []
  }
}

export function WatchlistPage({ onOpenResearch }: { onOpenResearch: (code: string) => void }) {
  const reduceMotion = useReducedMotion()
  const queryClient = useQueryClient()
  const [code, setCode] = useState('')
  const [deleteCodes, setDeleteCodes] = useState<string[] | null>(null)
  const items = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist })
  const selection = useRowSelection(items.data?.map((item) => item.code) ?? [])
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['watchlist'] })
  const add = useMutation({
    mutationFn: (stockCode: string) => api.addWatchlist(stockCode),
    onSuccess: async () => { setCode(''); await refresh() },
  })
  const update = useMutation({
    mutationFn: ({ stockCode, note }: { stockCode: string; note: string }) => api.updateWatchlist(stockCode, note),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (codes: string[]) => codes.length === 1 ? api.deleteWatchlist(codes[0]) : api.deleteWatchlistItems(codes),
    onSuccess: async () => {
      setDeleteCodes(null)
      selection.clear()
      await refresh()
    },
  })
  const migrate = useMutation({
    mutationFn: api.importWatchlist,
    onSuccess: async () => { localStorage.removeItem(legacyKey); await refresh() },
  })

  useEffect(() => {
    if (!items.isSuccess || migrate.isPending || migrate.isSuccess) return
    const legacy = readLegacyWatchlist()
    if (legacy.length) migrate.mutate(legacy)
  }, [items.isSuccess, migrate])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const normalized = code.trim()
    if (/^\d{6}$/.test(normalized)) add.mutate(normalized)
  }
  const error = items.error ?? add.error ?? update.error ?? remove.error ?? migrate.error

  return <div className="flex flex-col gap-4">
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Star />自选股</CardTitle><CardDescription>保存在本机 SQLite 中，行情与财务数据仍按需读取。</CardDescription><CardAction><AnimatePresence initial={false}>{selection.selected.size ? <motion.div key="bulk-actions" initial={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} transition={reduceMotion ? reducedFadeTransition : { y: spatialSpring, opacity: reducedFadeTransition }} className="flex items-center gap-2"><span className="whitespace-nowrap text-sm text-muted-foreground tabular-nums">已选 {selection.selected.size} 项</span><Button variant="destructive" size="sm" onClick={() => setDeleteCodes([...selection.selected])}><Trash2 data-icon="inline-start" />批量移除</Button></motion.div> : null}</AnimatePresence></CardAction></CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={submit}>
          <FieldGroup>
            <Field data-invalid={Boolean(code && !/^\d{6}$/.test(code.trim()))}>
              <FieldLabel htmlFor="watchlist-code">证券代码</FieldLabel>
              <div className="flex items-center gap-2">
                <Input id="watchlist-code" value={code} onChange={(event) => setCode(event.currentTarget.value)} inputMode="numeric" maxLength={6} placeholder="例如 600519" aria-invalid={Boolean(code && !/^\d{6}$/.test(code.trim()))} />
                <Button type="submit" disabled={!/^\d{6}$/.test(code.trim()) || add.isPending}>{add.isPending ? <Spinner data-icon="inline-start" /> : <Plus data-icon="inline-start" />}加入自选</Button>
              </div>
              {code && !/^\d{6}$/.test(code.trim()) ? <FieldError>请输入 6 位证券代码。</FieldError> : null}
            </Field>
          </FieldGroup>
        </form>

        {error ? <Alert variant="destructive"><AlertTitle>自选股暂时无法更新</AlertTitle><AlertDescription>{error.message}</AlertDescription></Alert> : null}
        {items.isPending || migrate.isPending ? <div className="grid min-h-40 place-items-center"><Spinner /></div> : null}
        {items.isSuccess && !migrate.isPending && items.data.length === 0 ? <EmptyState title="还没有自选股" description="输入证券代码，将想继续跟踪的公司加入这里。" /> : null}
        {items.data?.length ? <Table className="min-w-[640px]">
        <TableHeader><TableRow><TableHead className="w-10"><Checkbox aria-label="选择全部自选股" checked={selection.allSelected} indeterminate={selection.someSelected} onCheckedChange={selection.toggleAll} /></TableHead><TableHead>证券</TableHead><TableHead>研究备注</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
        <TableBody>{items.data.map((item) => <TableRow key={item.code}>
          <TableCell><Checkbox aria-label={`选择 ${item.name}`} checked={selection.selected.has(item.code)} onCheckedChange={(checked) => selection.toggle(item.code, checked)} /></TableCell>
          <TableCell><div className="flex min-w-0 flex-col"><span className="truncate font-medium" title={item.name}>{item.name}</span><span className="font-mono text-xs text-muted-foreground">{item.code}</span></div></TableCell>
          <TableCell><Input aria-label={`${item.name}研究备注`} defaultValue={item.note} maxLength={500} onBlur={(event) => { const note = event.currentTarget.value.trim(); if (note !== item.note) update.mutate({ stockCode: item.code, note }) }} /></TableCell>
          <TableCell><div className="flex justify-end gap-1"><Tooltip><TooltipTrigger render={<Button variant="outline" size="icon-sm" />} aria-label="打开研究" onClick={() => onOpenResearch(item.code)}><ArrowUpRight /></TooltipTrigger><TooltipContent>打开研究</TooltipContent></Tooltip><Tooltip><TooltipTrigger render={<Button variant="outline" size="icon-sm" className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive" />} aria-label="移除自选股" disabled={remove.isPending} onClick={() => setDeleteCodes([item.code])}><Trash2 /></TooltipTrigger><TooltipContent>移除自选股</TooltipContent></Tooltip></div></TableCell>
        </TableRow>)}</TableBody>
      </Table> : null}</CardContent>
    </Card>
    <AlertDialog open={Boolean(deleteCodes)} onOpenChange={(open) => { if (remove.isPending) return; remove.reset(); if (!open) setDeleteCodes(null) }}>
      <AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>{(deleteCodes?.length ?? 0) > 1 ? `移除所选 ${deleteCodes?.length} 只自选股？` : '移除这只自选股？'}</AlertDialogTitle><AlertDialogDescription>仅从自选股列表移除，不会删除历史研究记录。</AlertDialogDescription></AlertDialogHeader>
        {remove.error ? <Alert variant="destructive"><CircleAlert /><AlertTitle>移除失败</AlertTitle><AlertDescription>{remove.error.message}</AlertDescription></Alert> : null}
        <AlertDialogFooter><AlertDialogCancel disabled={remove.isPending}>取消</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={remove.isPending || !deleteCodes?.length} onClick={() => deleteCodes && remove.mutate(deleteCodes)}>{remove.isPending ? <Spinner data-icon="inline-start" /> : <Trash2 data-icon="inline-start" />}移除</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
}
