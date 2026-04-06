import { useEffect, useRef } from 'react'
import { useSimulationStore } from '../../stores/simulationStore'

export default function TimelineSlider() {
  const { frames, currentFrameIndex, isPlaying, setFrameIndex, togglePlayback } = useSimulationStore()
  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    if (isPlaying && frames) {
      intervalRef.current = window.setInterval(() => {
        useSimulationStore.setState((s) => {
          const next = s.currentFrameIndex + 1
          if (next >= (s.frames?.frames.length ?? 0)) {
            return { isPlaying: false, currentFrameIndex: 0 }
          }
          return { currentFrameIndex: next }
        })
      }, 500)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [isPlaying, frames])

  if (!frames || frames.frames.length === 0) return null

  const currentFrame = frames.frames[currentFrameIndex]
  const totalFrames = frames.frames.length
  const timeMinutes = currentFrame ? Math.round(currentFrame.time_s / 60) : 0

  return (
    <div className="absolute bottom-4 left-4 right-4 z-10 flex items-center gap-3 rounded bg-slate-800/95 px-4 py-2">
      <button
        onClick={togglePlayback}
        className="flex h-8 w-8 items-center justify-center rounded bg-blue-600 text-sm hover:bg-blue-500"
      >
        {isPlaying ? '\u23F8' : '\u25B6'}
      </button>
      <input
        type="range"
        min={0}
        max={totalFrames - 1}
        value={currentFrameIndex}
        onChange={(e) => setFrameIndex(Number(e.target.value))}
        className="flex-1"
      />
      <span className="min-w-[80px] text-right text-xs text-slate-300">
        t = {timeMinutes} min
      </span>
    </div>
  )
}
