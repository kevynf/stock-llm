import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, CircleAlert, Eye, History, Trash2 } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { api } from '../api'
import { EmptyState } from '../components/EmptyState'
import { SourceStatus } from '../components/Status'
import { formatDataDate } from '@/lib/date'
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
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { contentOffset, reducedFadeTransition, spatialSpring } from '@/lib/motion'

export function HistoryPage({ onOpenRun }: { onOpenRun: (runId: string) => void }) {
  const reduceMotion = useReducedMotion()
  const queryClient = useQueryClient()
  const [deleteRunIds, setDeleteRunIds] = useState<string[] | null>(null)
  const runs = useQuery({ queryKey: ['runs'], queryFn: api.runs })
  const selection = useRowSelection(runs.data?.map((run) => run.id) ?? [])
  const deleteRun = useMutation({
    mutationFn: (ids: string[]) => ids.length === 1 ? api.deleteRun(ids[0]) : api.deleteRuns(ids),
    onSuccess: async () => {
      setDeleteRunIds(null)
      selection.clear()
      await queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })

  return <div className="flex flex-col gap-4">
    {runs.data?.length ? <Card>
      <CardHeader><CardTitle>研究记录</CardTitle><CardDescription>这里保存每次研究使用的数据和结果。</CardDescription><CardAction><AnimatePresence initial={false}>{selection.selected.size ? <motion.div key="bulk-actions" initial={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduceMotion ? 0 : -contentOffset }} transition={reduceMotion ? reducedFadeTransition : { y: spatialSpring, opacity: reducedFadeTransition }} className="flex items-center gap-2"><span className="whitespace-nowrap text-sm text-muted-foreground tabular-nums">已选 {selection.selected.size} 项</span><Button variant="destructive" size="sm" onClick={() => setDeleteRunIds([...selection.selected])}><Trash2 data-icon="inline-start" />批量删除</Button></motion.div> : null}</AnimatePresence></CardAction></CardHeader>
      <CardContent><Table className="min-w-[720px]">
        <TableHeader><TableRow><TableHead className="w-10"><Checkbox aria-label="选择全部研究记录" checked={selection.allSelected} indeterminate={selection.someSelected} onCheckedChange={selection.toggleAll} /></TableHead><TableHead>首位候选</TableHead><TableHead>研究视角</TableHead><TableHead className="text-right">候选数</TableHead><TableHead>数据状态</TableHead><TableHead>研究日期</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
        <TableBody>{runs.data.map((run) => { const preferred = run.ai_selection.top_three[0]; return <TableRow key={run.id}>
          <TableCell><Checkbox aria-label={`选择 ${preferred?.name ?? '研究记录'}`} checked={selection.selected.has(run.id)} onCheckedChange={(checked) => selection.toggle(run.id, checked)} /></TableCell>
          <TableCell><div className="flex flex-col"><span className="font-medium">{preferred?.name ?? '未形成首选'}</span>{preferred ? <span className="font-mono text-xs text-muted-foreground">{preferred.code}</span> : null}</div></TableCell>
          <TableCell>{run.request.strategy === 'trend' ? '趋势' : run.request.strategy === 'quality' ? '质量' : '平稳'}</TableCell>
          <TableCell className="whitespace-nowrap text-right font-mono tabular-nums">{run.candidate_count} 只</TableCell>
          <TableCell><SourceStatus status={run.provider.status} /></TableCell>
          <TableCell><span className="flex items-center gap-2 whitespace-nowrap tabular-nums"><CalendarDays />{formatDataDate(run.request.as_of)}</span></TableCell>
          <TableCell><div className="flex justify-end gap-2">
            <Tooltip><TooltipTrigger render={<Button variant="outline" size="icon-sm" />} aria-label="查看报告" onClick={() => onOpenRun(run.id)}><Eye /></TooltipTrigger><TooltipContent>查看报告</TooltipContent></Tooltip>
            <Tooltip><TooltipTrigger render={<Button variant="outline" size="icon-sm" className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive" />} aria-label="删除研究记录" onClick={() => setDeleteRunIds([run.id])}><Trash2 /></TooltipTrigger><TooltipContent>删除研究记录</TooltipContent></Tooltip>
          </div></TableCell>
        </TableRow>})}</TableBody>
      </Table></CardContent>
    </Card> : <Card><CardContent><EmptyState title="还没有研究记录" description="完成一次研究后，结果会保存在这里。" /></CardContent></Card>}
    <AlertDialog open={Boolean(deleteRunIds)} onOpenChange={(open) => { if (deleteRun.isPending) return; deleteRun.reset(); if (!open) setDeleteRunIds(null) }}>
      <AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>{(deleteRunIds?.length ?? 0) > 1 ? `删除所选 ${deleteRunIds?.length} 条研究记录？` : '删除这次研究？'}</AlertDialogTitle><AlertDialogDescription>报告、事件记录和关联对话将从本机永久删除。</AlertDialogDescription></AlertDialogHeader>
        {deleteRun.error ? <Alert variant="destructive"><CircleAlert /><AlertTitle>删除失败</AlertTitle><AlertDescription>{deleteRun.error.message}</AlertDescription></Alert> : null}
        <AlertDialogFooter><AlertDialogCancel disabled={deleteRun.isPending}>取消</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={deleteRun.isPending || !deleteRunIds?.length} onClick={() => deleteRunIds && deleteRun.mutate(deleteRunIds)}>{deleteRun.isPending ? <Spinner data-icon="inline-start" /> : <Trash2 data-icon="inline-start" />}删除</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    <Alert><History /><AlertTitle>历史记录如何使用</AlertTitle><AlertDescription>记录只包含研究当天能看到的信息，不计算胜率，也不会自动调整股票。</AlertDescription></Alert>
  </div>
}
