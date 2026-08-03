import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, MessageSquareMore, Trash2 } from 'lucide-react'
import { api } from '../api'
import { EmptyState } from './EmptyState'
import { formatDataTime } from '@/lib/date'
import { useRowSelection } from '@/hooks/use-row-selection'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export function ChatHistoryList({
  enabled = true,
  currentChatId,
  onOpenChat,
  onDeleted,
}: {
  enabled?: boolean
  currentChatId?: string
  onOpenChat: (chatId: string) => void
  onDeleted?: (chatIds: string[]) => void
}) {
  const queryClient = useQueryClient()
  const [deleteChatIds, setDeleteChatIds] = useState<string[] | null>(null)
  const chats = useQuery({ queryKey: ['chats'], queryFn: api.chats, enabled })
  const selection = useRowSelection(chats.data?.map((chat) => chat.id) ?? [])
  const remove = useMutation({
    mutationFn: async (ids: string[]) => {
      if (ids.length === 1) await api.deleteChat(ids[0])
      else await api.deleteChats(ids)
    },
    onSuccess: async (_, ids) => {
      setDeleteChatIds(null)
      selection.clear()
      onDeleted?.(ids)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['chats'] }),
        queryClient.invalidateQueries({ queryKey: ['latest-chat'] }),
      ])
    },
  })

  return <div className="flex min-h-0 flex-1 flex-col gap-4">
    {selection.selected.size ? <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-muted-foreground tabular-nums">已选 {selection.selected.size} 项</span>
      <Button variant="destructive" size="sm" onClick={() => setDeleteChatIds([...selection.selected])}><Trash2 data-icon="inline-start" />批量删除</Button>
    </div> : null}
    <ScrollArea scrollbars="both" className="h-full min-h-0 flex-1">
      {chats.isPending ? <div className="grid min-h-40 place-items-center"><Spinner /></div> : null}
      {chats.error ? <Alert variant="destructive"><CircleAlert /><AlertTitle>无法读取对话记录</AlertTitle><AlertDescription>{chats.error.message}</AlertDescription></Alert> : null}
      {chats.data?.length ? <Table className="min-w-[680px]">
        <TableHeader><TableRow>
          <TableHead className="w-10"><Checkbox aria-label="选择全部对话" checked={selection.allSelected} indeterminate={selection.someSelected} onCheckedChange={selection.toggleAll} /></TableHead>
          <TableHead>研究上下文</TableHead><TableHead>首条问题</TableHead><TableHead className="text-right">消息数</TableHead><TableHead>最近更新</TableHead><TableHead className="text-right">操作</TableHead>
        </TableRow></TableHeader>
        <TableBody>{chats.data.map((chat) => <TableRow key={chat.id} data-state={chat.id === currentChatId ? 'selected' : undefined}>
          <TableCell><Checkbox aria-label={`选择 ${chat.stock_code ? `个股 ${chat.stock_code}` : '选股研究'} 对话`} checked={selection.selected.has(chat.id)} onCheckedChange={(checked) => selection.toggle(chat.id, checked)} /></TableCell>
          <TableCell><div className="flex flex-col"><span className="font-medium">{chat.stock_code ? '个股研究' : '选股研究'}</span>{chat.stock_code ? <span className="font-mono text-xs text-muted-foreground">{chat.stock_code}</span> : null}</div></TableCell>
          <TableCell className="max-w-72 whitespace-normal"><span className="line-clamp-2 text-muted-foreground">{chat.preview || '尚无消息'}</span></TableCell>
          <TableCell className="whitespace-nowrap text-right font-mono tabular-nums">{chat.message_count} 条</TableCell>
          <TableCell className="whitespace-nowrap text-muted-foreground tabular-nums">{formatDataTime(chat.updated_at)}</TableCell>
          <TableCell><div className="flex justify-end gap-2">
            <Tooltip><TooltipTrigger render={<Button variant="outline" size="icon-sm" />} aria-label="继续对话" onClick={() => onOpenChat(chat.id)}><MessageSquareMore /></TooltipTrigger><TooltipContent>继续对话</TooltipContent></Tooltip>
            <Tooltip><TooltipTrigger render={<Button variant="outline" size="icon-sm" className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive" />} aria-label="删除对话" onClick={() => setDeleteChatIds([chat.id])}><Trash2 /></TooltipTrigger><TooltipContent>删除对话</TooltipContent></Tooltip>
          </div></TableCell>
        </TableRow>)}</TableBody>
      </Table> : chats.isSuccess ? <EmptyState title="还没有对话记录" description="开始一次研究对话后，会话会显示在这里。" /> : null}
    </ScrollArea>
    <AlertDialog open={Boolean(deleteChatIds)} onOpenChange={(nextOpen) => { if (remove.isPending) return; remove.reset(); if (!nextOpen) setDeleteChatIds(null) }}>
      <AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>{(deleteChatIds?.length ?? 0) > 1 ? `删除所选 ${deleteChatIds?.length} 条对话？` : '删除这条对话？'}</AlertDialogTitle><AlertDialogDescription>对话和其中的全部消息将从本机永久删除，研究报告不会受到影响。</AlertDialogDescription></AlertDialogHeader>
        {remove.error ? <Alert variant="destructive"><CircleAlert /><AlertTitle>删除失败</AlertTitle><AlertDescription>{remove.error.message}</AlertDescription></Alert> : null}
        <AlertDialogFooter><AlertDialogCancel disabled={remove.isPending}>取消</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={remove.isPending || !deleteChatIds?.length} onClick={() => deleteChatIds && remove.mutate(deleteChatIds)}>{remove.isPending ? <Spinner data-icon="inline-start" /> : <Trash2 data-icon="inline-start" />}删除</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
}
