import { useState } from 'react'

const API_BASE = 'http://127.0.0.1:5001/api'

interface LicenseGateProps {
  onActivated: () => Promise<void>
}

export default function LicenseGate({ onActivated }: LicenseGateProps) {
  const [licenseKey, setLicenseKey] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleActivate = async () => {
    const trimmedKey = licenseKey.trim()
    if (!trimmedKey) {
      return
    }

    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: trimmedKey })
      })
      const data = await res.json()
      if (data.success) {
        await onActivated()
      }
    } catch (err) {
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <div className="w-full max-w-md bg-white border rounded-xl p-6 space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">软件激活</h1>
          <p className="text-sm text-gray-500">请输入许可证密钥以继续使用。</p>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">许可证密钥</label>
          <input
            type="text"
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            placeholder="请输入许可证密钥"
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        <button
          onClick={handleActivate}
          disabled={submitting}
          className="w-full px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-60"
        >
          {submitting ? '激活中...' : '激活'}
        </button>
      </div>
    </div>
  )
}
