import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Play, Square, RefreshCw, CheckCircle, Circle } from 'lucide-react'

interface Shop {
  id: number
  shop_id: string
  name: string
  product_count: number
}

interface Account {
  id: number
  username: string
  is_online: boolean
}

interface TaskStatus {
  is_running: boolean
  is_paused: boolean
  shop_id: number | null
  channel_id: string | null
  total_products: number
  sent_count: number
  current_product: string | null
  current_account: string | null
  started_at: string | null
  last_sent_at: string | null
  error: string | null
}

const API_BASE = 'http://127.0.0.1:5001/api'

export default function AutoSenderPage() {
  const [shops, setShops] = useState<Shop[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [status, setStatus] = useState<TaskStatus | null>(null)
  const previousStatusRef = useRef<TaskStatus | null>(null)

  // 表单状态
  const [selectedShop, setSelectedShop] = useState('')
  const [targetChannel, setTargetChannel] = useState('')
  const [selectedAccounts, setSelectedAccounts] = useState<number[]>([])
  const [sendInterval, setSendInterval] = useState('60')
  const [loading, setLoading] = useState(false)

  const currentShop = status?.shop_id
    ? shops.find((shop) => shop.id === status.shop_id) || null
    : null

  // 获取店铺和账号数据
  const fetchData = async () => {
    try {
      const [shopsRes, accountsRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/shops`),
        fetch(`${API_BASE}/accounts`),
        fetch(`${API_BASE}/sender/status`)
      ])

      const shopsData = await shopsRes.json()
      const accountsData = await accountsRes.json()
      const statusData = await statusRes.json()

      if (shopsData.success) {
        setShops(shopsData.shops || [])
      }
      if (accountsData.success) {
        // 只显示在线账号
        const onlineAccounts = (accountsData.accounts || []).filter(
          (a: Account) => a.is_online
        )
        setAccounts(onlineAccounts)
      }
      if (statusData.success) {
        setStatus(statusData.status)
      }
    } catch (error) {
      console.error('获取数据失败:', error)
    }
  }

  useEffect(() => {
    fetchData()
    // 定期刷新状态
    const timer = window.setInterval(fetchData, 3000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (accounts.length === 0) {
      setSelectedAccounts([])
      return
    }
    setSelectedAccounts((prev) => prev.filter((id) => accounts.some((a) => a.id === id)))
  }, [accounts])

  useEffect(() => {
    const savedShop = localStorage.getItem('autoSender.selectedShop')
    const savedChannel = localStorage.getItem('autoSender.targetChannel')
    if (savedShop) {
      setSelectedShop(savedShop)
    }
    if (savedChannel) {
      setTargetChannel(savedChannel)
    }
  }, [])

  useEffect(() => {
    if (!status) return
    if (status.shop_id && (status.is_running || status.is_paused || !selectedShop)) {
      setSelectedShop(String(status.shop_id))
    }
    if (status.channel_id && (status.is_running || status.is_paused || !targetChannel)) {
      setTargetChannel(status.channel_id)
    }
  }, [status, selectedShop, targetChannel])

  useEffect(() => {
    if (selectedShop) {
      localStorage.setItem('autoSender.selectedShop', selectedShop)
    }
  }, [selectedShop])

  useEffect(() => {
    if (targetChannel) {
      localStorage.setItem('autoSender.targetChannel', targetChannel)
    }
  }, [targetChannel])

  useEffect(() => {
    if (!status) {
      previousStatusRef.current = status
      return
    }
    const previousStatus = previousStatusRef.current
    if (previousStatus?.is_running && !status.is_running) {
      if (status.error) {
        toast.error(`任务异常: ${status.error}`)
      } else if (status.is_paused) {
        toast.success('任务已暂停')
      } else if (status.total_products > 0 && status.sent_count >= status.total_products) {
        toast.success('任务已完成')
      } else {
        toast.success('任务已停止')
      }
    }
    previousStatusRef.current = status
  }, [status])

  const toggleAccount = (id: number) => {
    setSelectedAccounts((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const parseChannelIds = (value: string) =>
    value
      .split(/[\s,]+/)
      .map((item) => item.trim())
      .filter(Boolean)

  const allSelected =
    accounts.length > 0 && accounts.every((account) => selectedAccounts.includes(account.id))

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedAccounts([])
      return
    }
    setSelectedAccounts(accounts.map((account) => account.id))
  }

  const handleStart = async () => {
    if (!selectedShop) {
      toast.error('请选择店铺')
      return
    }
    if (!targetChannel) {
      toast.error('请输入目标频道 ID')
      return
    }
    if (selectedAccounts.length === 0) {
      toast.error('请选择至少一个账号')
      return
    }
    const channelIds = parseChannelIds(targetChannel)
    if (channelIds.length === 0) {
      toast.error('请输入目标频道 ID')
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/sender/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shopId: selectedShop,
          channelIds,
          accountIds: selectedAccounts,
          interval: parseInt(sendInterval)
        })
      })
      const data = await res.json()
      if (data.success) {
        toast.success('自动发送已启动')
        fetchData()
      } else {
        toast.error(data.error || '启动失败')
      }
    } catch (error) {
      toast.error('启动失败')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/sender/stop`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        toast.success('已停止发送')
        fetchData()
      } else {
        toast.error(data.error || '停止失败')
      }
    } catch (error) {
      toast.error('停止失败')
    } finally {
      setLoading(false)
    }
  }

  const handlePause = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/sender/pause`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        toast.success('任务已暂停')
        fetchData()
      } else {
        toast.error(data.error || '暂停失败')
      }
    } catch (error) {
      toast.error('暂停失败')
    } finally {
      setLoading(false)
    }
  }

  const handleResume = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/sender/resume`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        toast.success('任务继续运行中...')
        fetchData()
      } else {
        toast.error(data.error || '继续失败')
      }
    } catch (error) {
      toast.error('继续失败')
    } finally {
      setLoading(false)
    }
  }

  const isRunning = status?.is_running || false
  const isPaused = status?.is_paused || false

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">自动发送控制台</h2>
          <p className="text-gray-500">配置并启动自动发送任务</p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 bg-white border rounded-lg hover:bg-gray-50"
        >
          <RefreshCw size={18} />
          刷新
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 左侧：配置区 */}
        <div className="bg-white rounded-lg border p-6">
          <h3 className="text-lg font-bold text-gray-800 mb-4">任务配置</h3>

          <div className="space-y-4">
            {/* 选择店铺 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                选择店铺 (数据源)
              </label>
              <select
                value={selectedShop}
                onChange={(e) => setSelectedShop(e.target.value)}
                disabled={isRunning || isPaused}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              >
                <option value="">选择要发送的店铺</option>
                {shops.map((shop) => (
                  <option key={shop.id} value={shop.id}>
                    {shop.name} ({shop.product_count || 0} 个商品)
                  </option>
                ))}
              </select>
            </div>

            {/* 目标频道 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                目标 Discord 频道 ID（可多个，逗号或空格分隔）
              </label>
              <input
                type="text"
                value={targetChannel}
                onChange={(e) => setTargetChannel(e.target.value)}
                disabled={isRunning || isPaused}
                placeholder="例如: 123456789012345678, 234567890123456789"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              />
            </div>

            {/* 发送频率 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                发送间隔 (秒)
              </label>
              <input
                type="number"
                value={sendInterval}
                onChange={(e) => setSendInterval(e.target.value)}
                disabled={isRunning || isPaused}
                min="10"
                max="3600"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500">建议设置 60 秒以上，避免触发限制</p>
            </div>

            {/* 操作按钮 */}
            <div className="pt-4 flex gap-4">
              <button
                onClick={handleStart}
                disabled={isRunning || isPaused || loading}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Play size={18} />
                启动任务
              </button>
              <button
                onClick={isPaused ? handleResume : handlePause}
                disabled={loading || (!isRunning && !isPaused)}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-white bg-amber-500 rounded-lg hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isPaused ? '继续任务' : '暂停任务'}
              </button>
              <button
                onClick={handleStop}
                disabled={(!isRunning && !isPaused) || loading}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Square size={18} />
                停止任务
              </button>
            </div>
          </div>
        </div>

        {/* 右侧：账号选择区 */}
        <div className="bg-white rounded-lg border p-6">
          <h3 className="text-lg font-bold text-gray-800 mb-4">账号轮换池</h3>

          {accounts.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              暂无在线账号，请在账号管理页启动账号
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between text-sm text-gray-500 mb-2">
                <span>在线账号 {accounts.length}</span>
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  disabled={isRunning || isPaused}
                  className="text-blue-600 hover:text-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {allSelected ? '全不选' : '全选'}
                </button>
              </div>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {accounts.map((account) => (
                  <div
                    key={account.id}
                    onClick={() => !(isRunning || isPaused) && toggleAccount(account.id)}
                    className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedAccounts.includes(account.id)
                        ? 'bg-blue-50 border-blue-200 border'
                        : 'bg-gray-50 hover:bg-gray-100'
                    } ${isRunning || isPaused ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {selectedAccounts.includes(account.id) ? (
                      <CheckCircle size={20} className="text-blue-600" />
                    ) : (
                      <Circle size={20} className="text-gray-400" />
                    )}
                    <div className="flex-1">
                      <span className="font-medium text-gray-800">
                        {account.username || `账号 ${account.id}`}
                      </span>
                      <span className="ml-2 text-xs text-green-600">在线</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <p className="mt-4 text-xs text-gray-500">
            系统将按照勾选顺序，每隔 {sendInterval} 秒切换下一个账号发送一条链接
          </p>
        </div>
      </div>

      {/* 任务状态 */}
      {status && (
        <div className="bg-white rounded-lg border p-6">
          <h3 className="text-lg font-bold text-gray-800 mb-4">任务状态</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div>
              <p className="text-sm text-gray-500">状态</p>
              <p
                className={`font-medium ${
                  isRunning ? 'text-green-600' : isPaused ? 'text-amber-600' : 'text-gray-600'
                }`}
              >
                {isRunning ? '运行中' : isPaused ? '已暂停' : '已停止'}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">进度</p>
              <p className="font-medium text-gray-800">
                {status.sent_count} / {status.total_products}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">当前店铺</p>
              <p className="font-medium text-gray-800 truncate">
                {currentShop ? `${currentShop.name} (${currentShop.shop_id})` : status.shop_id || '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">目标频道</p>
              <p className="font-medium text-gray-800 truncate">{status.channel_id || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">当前商品ID</p>
              <p className="font-medium text-gray-800 truncate">
                {status.current_product || '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">当前账号</p>
              <p className="font-medium text-gray-800">{status.current_account || '-'}</p>
            </div>
          </div>
          {status.error && (
            <div className="mt-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm">
              {status.error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
