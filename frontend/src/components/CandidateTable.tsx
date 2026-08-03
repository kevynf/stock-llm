import { Fragment, useMemo, useState } from 'react'
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { ArrowUpRight, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { Candidate } from '../types'
import { CheckStatus } from './Status'

const column = createColumnHelper<Candidate>()

export function CandidateTable({ candidates, selectedCode, onSelect, onResearch }: {
  candidates: Candidate[]
  selectedCode?: string
  onSelect: (candidate: Candidate) => void
  onResearch: (code: string) => void
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const columns = useMemo(() => [
    column.display({ id: 'rank', header: () => <span className="block text-center">排名</span>, cell: (info) => <span className="block text-center tabular-nums">{info.row.index + 1}</span> }),
    column.accessor('name', { header: '股票', cell: (info) => <div className="flex max-w-48 min-w-0 flex-col"><span className="truncate font-medium" title={info.getValue()}>{info.getValue()}</span><span className="truncate font-mono text-xs text-muted-foreground" title={`${info.row.original.code} · ${info.row.original.sector}`}>{info.row.original.code} · {info.row.original.sector}</span></div> }),
    column.accessor('price', { header: () => <span className="block text-right">最新价</span>, cell: (info) => <span className="block whitespace-nowrap text-right font-mono tabular-nums">{info.getValue().toFixed(2)} 元</span> }),
    column.accessor('change_pct', { header: () => <span className="block text-right">当日涨跌</span>, cell: (info) => <span className={cn('block whitespace-nowrap text-right font-mono tabular-nums', info.getValue() > 0 ? 'text-stock-up' : info.getValue() < 0 ? 'text-stock-down' : 'text-muted-foreground')}>{info.getValue() > 0 ? '+' : ''}{info.getValue().toFixed(2)}%</span> }),
    column.accessor('passed', { header: () => <span className="block text-right">通过</span>, cell: (info) => <span className="block whitespace-nowrap text-right font-mono text-status-live tabular-nums">{info.getValue()} 项</span> }),
    column.accessor('concerns', { header: () => <span className="block text-right">关注</span>, cell: (info) => <span className="block whitespace-nowrap text-right font-mono text-status-cached tabular-nums">{info.getValue()} 项</span> }),
    column.display({ id: 'actions', header: () => <span className="block text-right">操作</span>, cell: (info) => <div className="flex justify-end gap-1">
      <Tooltip><TooltipTrigger render={<Button variant="ghost" size="icon" />} onClick={(event) => { event.stopPropagation(); onResearch(info.row.original.code) }} aria-label="查看股票详情"><ArrowUpRight /></TooltipTrigger><TooltipContent>查看股票详情</TooltipContent></Tooltip>
      <Tooltip><TooltipTrigger render={<Button variant="ghost" size="icon" />} onClick={(event) => { event.stopPropagation(); setExpanded((value) => value === info.row.original.code ? null : info.row.original.code) }} aria-label="查看检查结果">{expanded === info.row.original.code ? <ChevronUp /> : <ChevronDown />}</TooltipTrigger><TooltipContent>查看检查结果</TooltipContent></Tooltip>
    </div> }),
  ], [expanded, onResearch])
  const table = useReactTable({ data: candidates, columns, getCoreRowModel: getCoreRowModel() })

  return (
    <ScrollArea className="h-[420px] w-full">
      <Table className="min-w-[760px]">
        <TableHeader>{table.getHeaderGroups().map((group) => <TableRow key={group.id}>{group.headers.map((header) => <TableHead key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}</TableHeader>
        <TableBody>{table.getRowModel().rows.map((row) => <Fragment key={row.id}>
          <TableRow data-state={selectedCode === row.original.code ? 'selected' : undefined} onClick={() => onSelect(row.original)} className="cursor-pointer">
            {row.getVisibleCells().map((cell) => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}
          </TableRow>
          {expanded === row.original.code ? <TableRow><TableCell colSpan={7} className="whitespace-normal"><div className="candidate-checks">{row.original.checks.map((check) => <div key={check.label} className="flex min-w-0 items-start gap-2"><CheckStatus state={check.state} /><div className="flex min-w-0 flex-col gap-1"><span className="font-medium">{check.label}</span><span className="break-words text-sm text-muted-foreground">{check.reason}</span></div></div>)}</div></TableCell></TableRow> : null}
        </Fragment>)}</TableBody>
      </Table>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  )
}
