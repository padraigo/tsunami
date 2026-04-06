import { useEffect } from 'react'
import { useSimulationStore } from '../stores/simulationStore'

export default function ErrorToast() {
  const { error, setError } = useSimulationStore()

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error, setError])

  if (!error) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 rounded bg-red-600 px-4 py-2 text-sm shadow-lg">
      <span>{error}</span>
      <button onClick={() => setError(null)} className="ml-3 font-bold">✕</button>
    </div>
  )
}
