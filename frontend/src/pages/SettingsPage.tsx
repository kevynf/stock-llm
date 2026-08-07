import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clipboard, Download, ExternalLink, HardDrive, KeyRound, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { api, openDataDirectory } from '../api'
import type { StorageScope } from '../types'
import { AIConnectionStatus } from '../components/Status'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const allScopes: StorageScope[] = ['market', 'external_links', 'logs']

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function ModelSettings() {
  const config = useQuery({ queryKey: ['model-config'], queryFn: api.modelConfig })
  const [baseUrl, setBaseUrl] = useState('https://api.deepseek.com')
  const [model, setModel] = useState('deepseek-v4-flash')
  const [apiKey, setApiKey] = useState('')
  useEffect(() => {
    if (config.data) { setBaseUrl(config.data.base_url); setModel(config.data.model) }
  }, [config.data])
  const save = useMutation({
    mutationFn: () => api.saveModelConfig({ base_url: baseUrl, model, ...(apiKey ? { api_key: apiKey } : {}) }),
    onSuccess: () => { setApiKey(''); void config.refetch() },
  })
  const test = useMutation({ mutationFn: api.testModel, onSettled: () => void config.refetch() })
  const submit = (event: FormEvent) => { event.preventDefault(); save.mutate() }
  return <Card>
    <CardHeader>
      <CardTitle className="flex items-center gap-2"><KeyRound />DeepSeek</CardTitle>
      <CardDescription>使用 OpenAI 兼容的 Chat Completions 格式配置研究分析模型。</CardDescription>
      <CardAction><AIConnectionStatus configured={Boolean(config.data?.key_configured)} status={config.data?.connection_status} /></CardAction>
    </CardHeader>
    <form onSubmit={submit} className="contents">
      <CardContent><FieldGroup>
        <Field><FieldLabel htmlFor="base-url">Base URL</FieldLabel><Input id="base-url" value={baseUrl} onChange={(event) => setBaseUrl(event.currentTarget.value)} /></Field>
        <Field><FieldLabel htmlFor="model">模型</FieldLabel><Input id="model" value={model} onChange={(event) => setModel(event.currentTarget.value)} /></Field>
        <Field>
          <FieldLabel htmlFor="api-key">API 密钥</FieldLabel>
          <Input id="api-key" type="password" autoComplete="off" value={apiKey} onChange={(event) => setApiKey(event.currentTarget.value)} placeholder={config.data?.key_configured ? '保留现有密钥' : '输入 DeepSeek API 密钥'} />
          <FieldDescription>留空不会覆盖已经保存的密钥。</FieldDescription>
        </Field>
        <Alert><ShieldCheck /><AlertDescription>密钥只保存在 Windows Credential Manager 中，界面和诊断包都不会读取或导出密钥。</AlertDescription></Alert>
        {save.error ? <Alert variant="destructive"><AlertDescription>{save.error.message}</AlertDescription></Alert> : null}
        {test.data ? <Alert><AlertDescription>{test.data.message}</AlertDescription></Alert> : null}
        {test.error ? <Alert variant="destructive"><AlertDescription>{test.error.message}</AlertDescription></Alert> : null}
      </FieldGroup></CardContent>
      <CardFooter className="flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending}>{save.isPending ? <Spinner data-icon="inline-start" /> : null}保存设置</Button>
        <Button type="button" variant="outline" disabled={test.isPending || !config.data?.key_configured} onClick={() => test.mutate()}>{test.isPending ? <Spinner data-icon="inline-start" /> : null}测试连接</Button>
      </CardFooter>
    </form>
  </Card>
}

function StorageSettings() {
  const queryClient = useQueryClient()
  const storage = useQuery({ queryKey: ['system-storage'], queryFn: api.storage })
  const [pendingScopes, setPendingScopes] = useState<StorageScope[] | null>(null)
  const clear = useMutation({
    mutationFn: (scopes: StorageScope[]) => api.clearStorage(scopes),
    onSuccess: async () => {
      setPendingScopes(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['system-storage'] }),
        queryClient.invalidateQueries({ queryKey: ['system-logs'] }),
        queryClient.invalidateQueries({ queryKey: ['providers'] }),
        queryClient.invalidateQueries({ queryKey: ['stock'] }),
      ])
    },
  })
  const targetLabel = pendingScopes?.length === allScopes.length
    ? '全部临时数据'
    : storage.data?.categories.find((item) => item.scope === pendingScopes?.[0])?.label
  return <>
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><HardDrive />临时数据</CardTitle>
        <CardDescription>只清理可重新获取的缓存和日志，不会删除研究历史、对话、自选股、设置或密钥。</CardDescription>
        <CardAction><Button variant="outline" size="sm" onClick={() => setPendingScopes(allScopes)} disabled={clear.isPending}><Trash2 data-icon="inline-start" />清理全部</Button></CardAction>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow><TableHead>类别</TableHead><TableHead className="text-right">文件数</TableHead><TableHead className="text-right">占用空间</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
          <TableBody>{storage.data?.categories.map((item) => <TableRow key={item.scope}>
            <TableCell className="font-medium">{item.label}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">{item.file_count}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">{formatBytes(item.bytes)}</TableCell>
            <TableCell className="text-right"><Button variant="outline" size="sm" disabled={!item.file_count || clear.isPending} onClick={() => setPendingScopes([item.scope])}><Trash2 data-icon="inline-start" />清理</Button></TableCell>
          </TableRow>)}</TableBody>
        </Table>
        {storage.error ? <Alert variant="destructive"><AlertDescription>{storage.error.message}</AlertDescription></Alert> : null}
      </CardContent>
    </Card>
    <AlertDialog open={pendingScopes !== null} onOpenChange={(open) => { if (!open && !clear.isPending) setPendingScopes(null) }}>
      <AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>清理{targetLabel}？</AlertDialogTitle><AlertDialogDescription>这些文件可以重新获取。业务记录、设置和密钥不会受到影响。</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel disabled={clear.isPending}>取消</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={clear.isPending} onClick={() => pendingScopes && clear.mutate(pendingScopes)}>{clear.isPending ? <Spinner data-icon="inline-start" /> : null}确认清理</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </>
}

function DiagnosticsSettings() {
  const queryClient = useQueryClient()
  const diagnostics = useQuery({ queryKey: ['system-diagnostics'], queryFn: api.diagnostics })
  const [levelFilter, setLevelFilter] = useState('all')
  const logs = useQuery({ queryKey: ['system-logs', levelFilter], queryFn: () => api.logs(levelFilter === 'all' ? undefined : levelFilter) })
  const [confirmDetailed, setConfirmDetailed] = useState(false)
  const setLevel = useMutation({
    mutationFn: api.setLogLevel,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['system-diagnostics'] }),
  })
  const exportData = useMutation({
    mutationFn: api.exportDiagnostics,
    onSuccess: ({ blob, filename }) => { saveBlob(blob, filename); setConfirmDetailed(false) },
  })
  const systemText = useMemo(() => diagnostics.data ? [
    `StockLLM ${diagnostics.data.app_version}`,
    `${diagnostics.data.platform} (${diagnostics.data.architecture})`,
    `Python ${diagnostics.data.python_version}`,
    `运行模式：${diagnostics.data.runtime === 'desktop' ? 'Windows 桌面应用' : '浏览器开发模式'}`,
    `数据目录：${diagnostics.data.data_directory}`,
  ].join('\n') : '', [diagnostics.data])
  return <>
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader><CardTitle>运行状态</CardTitle><CardDescription>用于定位版本、环境和连接问题。</CardDescription></CardHeader>
        <CardContent>
          <Table><TableHeader><TableRow><TableHead>项目</TableHead><TableHead>当前值</TableHead></TableRow></TableHeader><TableBody>
            <TableRow><TableCell>应用版本</TableCell><TableCell className="font-mono">{diagnostics.data?.app_version ?? '—'}</TableCell></TableRow>
            <TableRow><TableCell>运行环境</TableCell><TableCell>{diagnostics.data ? `${diagnostics.data.platform} · ${diagnostics.data.architecture}` : '—'}</TableCell></TableRow>
            <TableRow><TableCell>Python</TableCell><TableCell className="font-mono">{diagnostics.data?.python_version ?? '—'}</TableCell></TableRow>
            <TableRow><TableCell>模型连接</TableCell><TableCell><Badge variant="outline">{diagnostics.data?.connections.model === 'connected' ? '已连接' : '未连接'}</Badge></TableCell></TableRow>
          </TableBody></Table>
        </CardContent>
        <CardFooter className="flex-wrap gap-2">
          <Button variant="outline" onClick={() => void navigator.clipboard.writeText(systemText)} disabled={!systemText}><Clipboard data-icon="inline-start" />复制系统信息</Button>
          <Button variant="outline" onClick={() => void openDataDirectory()} disabled={diagnostics.data?.runtime !== 'desktop'}><ExternalLink data-icon="inline-start" />打开数据目录</Button>
          <Button variant="outline" onClick={() => exportData.mutate('basic')} disabled={exportData.isPending}><Download data-icon="inline-start" />导出基础诊断包</Button>
          <Button variant="outline" onClick={() => setConfirmDetailed(true)} disabled={exportData.isPending}><Download data-icon="inline-start" />导出详细诊断包</Button>
        </CardFooter>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>运行日志</CardTitle>
          <CardDescription>详细日志只在本次运行期间生效，应用重启后恢复普通级别。</CardDescription>
          <CardAction><div className="flex items-center gap-2"><Select value={levelFilter} onValueChange={(value) => setLevelFilter(value ?? 'all')}><SelectTrigger size="sm"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="all">全部级别</SelectItem><SelectItem value="info">信息</SelectItem><SelectItem value="warning">警告</SelectItem><SelectItem value="error">错误</SelectItem></SelectGroup></SelectContent></Select><Button variant="outline" size="icon-sm" aria-label="刷新日志" onClick={() => void logs.refetch()}><RefreshCw /></Button></div></CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Field orientation="horizontal"><FieldLabel>日志级别</FieldLabel><Select value={diagnostics.data?.log_level ?? 'normal'} onValueChange={(value) => { if (value === 'normal' || value === 'detailed') setLevel.mutate(value) }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="normal">普通</SelectItem><SelectItem value="detailed">详细（本次运行）</SelectItem></SelectGroup></SelectContent></Select></Field>
          <ScrollArea className="h-80 rounded-lg border">
            <Table><TableHeader><TableRow><TableHead>时间</TableHead><TableHead>级别</TableHead><TableHead>组件</TableHead><TableHead>事件</TableHead><TableHead>信息</TableHead></TableRow></TableHeader><TableBody>{logs.data?.map((item, index) => <TableRow key={`${item.timestamp}-${index}`}>
              <TableCell className="font-mono text-xs">{new Date(item.timestamp).toLocaleString('zh-CN')}</TableCell><TableCell><Badge variant="outline">{item.level}</Badge></TableCell><TableCell>{item.component}</TableCell><TableCell>{item.event}</TableCell><TableCell className="max-w-md whitespace-normal">{item.message}</TableCell>
            </TableRow>)}</TableBody></Table>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
    <AlertDialog open={confirmDetailed} onOpenChange={setConfirmDetailed}>
      <AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>导出详细诊断包？</AlertDialogTitle><AlertDialogDescription>详细诊断包会额外包含研究快照、股票代码、提问和 AI 回复。它仍不会包含 API 密钥、Credential Manager 内容、认证头或外部新闻正文。请仅在确认需要时分享。</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel disabled={exportData.isPending}>取消</AlertDialogCancel><AlertDialogAction onClick={() => exportData.mutate('detailed')} disabled={exportData.isPending}>{exportData.isPending ? <Spinner data-icon="inline-start" /> : null}确认导出</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </>
}

export function SettingsPage() {
  return <div className="flex w-full flex-col gap-4">
    <ModelSettings />
    <StorageSettings />
    <DiagnosticsSettings />
  </div>
}
