import type { ReactNode } from 'react'

interface Props {
  sidebar: ReactNode
  map: ReactNode
  bottom?: ReactNode
  topBar: ReactNode
}

export default function Layout({ sidebar, map, bottom, topBar }: Props) {
  return (
    <div className="flex h-screen w-screen flex-col bg-slate-900 text-white">
      {topBar}
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-80 flex-shrink-0 overflow-y-auto border-r border-slate-700 bg-slate-800 p-4">
          {sidebar}
        </aside>
        <main className="relative flex-1">
          {map}
          {bottom && (
            <div className="absolute bottom-0 left-0 right-0 max-h-64 overflow-y-auto border-t border-slate-700 bg-slate-800/95 p-4">
              {bottom}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
