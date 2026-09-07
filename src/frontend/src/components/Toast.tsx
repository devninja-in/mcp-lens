import { useEffect } from 'react'

interface ToastProps {
  message: string
  type: 'success' | 'error' | 'info'
  onClose: () => void
}

export default function Toast({ message, type, onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000)
    return () => clearTimeout(timer)
  }, [onClose])

  const colors = {
    success: 'bg-green-100 border-green-400 text-green-800',
    error: 'bg-red-100 border-red-400 text-red-800',
    info: 'bg-blue-100 border-blue-400 text-blue-800',
  }

  return (
    <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded border ${colors[type]} max-w-md shadow-lg`}>
      <div className="flex justify-between items-start gap-2">
        <p className="text-sm">{message}</p>
        <button onClick={onClose} className="text-lg leading-none font-bold opacity-50 hover:opacity-100">&times;</button>
      </div>
    </div>
  )
}
