import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, CornerUpLeft, KeyRound, Maximize2, MessagesSquare, Minimize2, Send, Wrench } from 'lucide-react'
import { api } from '../api'
import type { ChatSession } from '../types'
import { MarkdownMessage } from './MarkdownMessage'
import { AIConnectionStatus, semanticBadgeClassName } from './Status'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

export function ResearchChat({
  runId,
  stockCode,
  initialChatId,
  onOpenChats,
  onBack,
  className,
}: {
  runId?: string
  stockCode?: string
  initialChatId?: string
  onOpenChats?: () => void
  onBack?: () => void
  className?: string
}) {
  const queryClient = useQueryClient()
  const [fullScreen, setFullScreen] = useState(false)
  const [selectedChatId, setSelectedChatId] = useState<string | null>(initialChatId ?? null)
  const [content, setContent] = useState('')
  const [skill, setSkill] = useState(stockCode ? 'explain_technical' : 'explain_preferred')
  const chatQueryKey = ['latest-chat', runId ?? null, stockCode ?? null] as const
  const skills = useQuery({ queryKey: ['skills'], queryFn: api.skills })
  const model = useQuery({ queryKey: ['model-config'], queryFn: api.modelConfig })
  const existing = useQuery({
    queryKey: chatQueryKey,
    queryFn: () => api.latestChat(runId, stockCode),
    enabled: Boolean(runId || stockCode),
  })
  const selectedChat = useQuery({
    queryKey: ['chat', selectedChatId],
    queryFn: () => api.chat(selectedChatId!),
    enabled: Boolean(selectedChatId),
  })
  const create = useMutation({
    mutationFn: () => api.createChat(runId, stockCode),
    onSuccess: (session) => {
      queryClient.setQueryData(chatQueryKey, session)
      void queryClient.invalidateQueries({ queryKey: ['chats'] })
    },
  })
  const chat = selectedChatId ? selectedChat.data ?? null : existing.data ?? create.data ?? null
  const chatPending = selectedChatId ? selectedChat.isPending : existing.isPending
  const send = useMutation({
    mutationFn: async () => {
      const session = chat ?? await api.createChat(runId, stockCode)
      return api.sendMessage(session.id, content, skill)
    },
    onSuccess: (session) => {
      if (selectedChatId) queryClient.setQueryData(['chat', selectedChatId], session)
      else queryClient.setQueryData(chatQueryKey, session)
      void queryClient.invalidateQueries({ queryKey: ['chats'] })
      setContent('')
    },
  })
  const submit = (event: FormEvent) => { event.preventDefault(); if (content.trim()) send.mutate() }
  const skillItems = skills.data?.filter((item) => !stockCode || !['explain_preferred', 'compare_top_three'].includes(item.id)).map((item) => ({ value: item.id, label: item.name })) ?? []
  const aiReady = Boolean(model.data?.key_configured)
  const returnFromSavedChat = () => onBack ? onBack() : setSelectedChatId(null)
  const openChatHistory = () => {
    setFullScreen(false)
    onOpenChats?.()
  }

  const conversation = <>
    {!aiReady ? <Alert><KeyRound /><AlertDescription>在“设置”中保存并测试 DeepSeek 密钥后即可提问。</AlertDescription></Alert> : null}
    <ScrollArea className="min-h-0 flex-1">
      {chatPending ? <div className="grid h-full place-items-center"><Spinner /></div> : chat?.messages.length ? <div className={cn('mx-auto flex w-full min-w-0 flex-col gap-2 px-4 py-2', fullScreen ? 'max-w-[90rem]' : 'max-w-5xl')}>{chat.messages.map((message) => <Card key={message.id} size="sm" className={cn('w-fit min-w-0', fullScreen ? 'max-w-[min(88%,64rem)]' : 'max-w-[min(82%,48rem)]', message.role === 'user' ? 'self-end' : 'self-start')}><CardContent className="min-w-0 max-w-full">{message.role === 'assistant' ? <div className="flex min-w-0 max-w-full flex-col gap-2"><Badge variant="outline" className={`self-start ${semanticBadgeClassName.info}`}>AI 生成</Badge><MarkdownMessage content={message.content} /></div> : <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content}</p>}{message.tool_traces.length ? <p className="mt-2 flex min-w-0 max-w-full flex-wrap items-center gap-1 break-words text-xs text-muted-foreground"><Wrench className="shrink-0" />{message.tool_traces.join(' · ')}</p> : null}</CardContent></Card>)}</div> : <Empty className="h-full"><EmptyHeader><EmptyMedia variant="icon"><Bot /></EmptyMedia><EmptyTitle>有问题可以继续问</EmptyTitle><EmptyDescription>AI 会根据当前研究数据和应用已读取的原文回答，并标明缺失或截断的信息。</EmptyDescription></EmptyHeader><EmptyContent><Button variant="outline" onClick={() => create.mutate()} disabled={create.isPending || chatPending || !aiReady || Boolean(selectedChatId)}>{create.isPending ? <Spinner data-icon="inline-start" /> : null}开始对话</Button></EmptyContent></Empty>}
    </ScrollArea>
  </>

  const composer = <form onSubmit={submit} className={cn('flex w-full flex-col gap-2', fullScreen && 'mx-auto max-w-[90rem]')}>
    <Select items={skillItems} value={skill} onValueChange={(value) => value && setSkill(value)}>
      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
      <SelectContent><SelectGroup>{skillItems.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectGroup></SelectContent>
    </Select>
    <InputGroup>
      <InputGroupInput value={content} onChange={(event) => setContent(event.currentTarget.value)} placeholder="输入想了解的理由、风险或数据来源…" aria-label="问题" disabled={chatPending} />
      <InputGroupAddon align="inline-end"><InputGroupButton type="submit" size="icon-xs" variant="default" disabled={send.isPending || chatPending || !content.trim() || !aiReady || (Boolean(selectedChatId) && !chat)} aria-label="发送">{send.isPending ? <Spinner /> : <Send />}</InputGroupButton></InputGroupAddon>
    </InputGroup>
  </form>

  return (
    <Dialog open={fullScreen} onOpenChange={setFullScreen}>
      {!fullScreen ? <Card className={cn('chat-panel', className)}>
        <CardHeader className="shrink-0">
          <CardTitle className="flex items-center gap-2"><Bot />研究对话</CardTitle>
          <CardDescription>{selectedChatId ? '正在查看已保存的对话' : chat ? '已连接到只读研究上下文' : '基于当前页面的来源和日期回答'}</CardDescription>
          <CardAction><div className="flex items-center gap-2"><AIConnectionStatus configured={aiReady} status={model.data?.connection_status} />{selectedChatId ? <Button variant="ghost" size="icon-sm" onClick={returnFromSavedChat} aria-label={onBack ? '返回对话记录' : '返回当前对话'} title={onBack ? '返回对话记录' : '返回当前对话'}><CornerUpLeft /></Button> : null}{onOpenChats ? <Button variant="ghost" size="icon-sm" onClick={openChatHistory} aria-label="打开对话记录" title="打开对话记录"><MessagesSquare /></Button> : null}<Button variant="ghost" size="icon-sm" onClick={() => setFullScreen(true)} aria-label="全屏显示对话" title="全屏显示对话"><Maximize2 /></Button></div></CardAction>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3">{conversation}</CardContent>
        <CardFooter className="shrink-0">{composer}</CardFooter>
      </Card> : null}
      <DialogContent showCloseButton={false} className="inset-0 top-0 left-0 flex h-svh w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none p-0 ring-inset sm:max-w-none">
        <DialogHeader className="grid shrink-0 grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b p-4 text-left">
          <div className="flex min-w-0 flex-col gap-1">
            <DialogTitle className="flex items-center gap-2"><Bot />研究对话</DialogTitle>
            <DialogDescription>{selectedChatId ? '正在查看已保存的对话' : chat ? '已连接到只读研究上下文' : '基于当前页面的来源和日期回答'}</DialogDescription>
          </div>
          <div className="flex items-center gap-2"><AIConnectionStatus configured={aiReady} status={model.data?.connection_status} />{selectedChatId ? <Button variant="ghost" size="icon-sm" onClick={returnFromSavedChat} aria-label={onBack ? '返回对话记录' : '返回当前对话'} title={onBack ? '返回对话记录' : '返回当前对话'}><CornerUpLeft /></Button> : null}{onOpenChats ? <Button variant="ghost" size="icon-sm" onClick={openChatHistory} aria-label="打开对话记录" title="打开对话记录"><MessagesSquare /></Button> : null}<Button variant="ghost" size="icon-sm" onClick={() => setFullScreen(false)} aria-label="退出全屏" title="退出全屏"><Minimize2 /></Button></div>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4">{conversation}</div>
        <div className="shrink-0 border-t bg-muted/50 p-4">{composer}</div>
      </DialogContent>
    </Dialog>
  )
}
