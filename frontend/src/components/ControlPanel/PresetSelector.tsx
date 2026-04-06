import type { Preset } from '../../types'

interface Props {
  presets: Preset[]
  onSelect: (preset: Preset) => void
}

export default function PresetSelector({ presets, onSelect }: Props) {
  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Presets</h3>
      <select
        defaultValue=""
        onChange={(e) => {
          const preset = presets.find((p) => p.name === e.target.value)
          if (preset) onSelect(preset)
        }}
        className="w-full rounded bg-slate-700 px-2 py-1 text-sm"
      >
        <option value="" disabled>Select a historic earthquake...</option>
        {presets.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name} (M{p.magnitude})
          </option>
        ))}
      </select>
    </div>
  )
}
