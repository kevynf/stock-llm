import { useEffect, useState } from 'react'

export function useRowSelection(ids: string[]) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const idsKey = ids.join('\u0000')

  useEffect(() => {
    const available = new Set(ids)
    setSelected((current) => {
      const next = new Set([...current].filter((id) => available.has(id)))
      return next.size === current.size ? current : next
    })
  }, [idsKey])

  const allSelected = ids.length > 0 && ids.every((id) => selected.has(id))
  const someSelected = !allSelected && ids.some((id) => selected.has(id))

  return {
    selected,
    allSelected,
    someSelected,
    clear: () => setSelected(new Set()),
    toggle: (id: string, checked: boolean) => setSelected((current) => {
      const next = new Set(current)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    }),
    toggleAll: (checked: boolean) => setSelected(checked ? new Set(ids) : new Set()),
  }
}
