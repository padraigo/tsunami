interface Props {
  onExport?: () => void
}

export default function TopBar({ onExport }: Props) {
  return (
    <header className="flex h-12 items-center justify-between border-b border-slate-700 bg-slate-800 px-4">
      <h1 className="text-lg font-bold tracking-wide">Tsunami Simulator</h1>
      <div className="flex gap-2">
        {onExport && (
          <button
            onClick={onExport}
            className="rounded bg-blue-600 px-3 py-1 text-sm hover:bg-blue-500"
          >
            Export GeoJSON
          </button>
        )}
      </div>
    </header>
  )
}
