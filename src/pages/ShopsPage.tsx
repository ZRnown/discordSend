import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2, Download, RefreshCw } from 'lucide-react'

interface Shop {
  id: number
  shop_id: string
  name: string
  product_count: number
  created_at: string
  updated_at: string
}

const API_BASE = 'http://127.0.0.1:5001/api'

export default function ShopsPage() {
  const [shops, setShops] = useState<Shop[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [newShopId, setNewShopId] = useState('')
  const scrapingStartsRef = useRef<Record<number, number>>({})

  const parseUpdatedAt = (value?: string) => {
    if (!value) return 0
    const normalized = value.includes('T') ? value : value.replace(' ', 'T')
    const parsed = Date.parse(normalized)
    return Number.isNaN(parsed) ? 0 : parsed
  }

  const fetchShops = async () => {
    try {
      const res = await fetch(`${API_BASE}/shops`)
      const data = await res.json()
      if (data.success) {
        const nextShops = data.shops || []
        setShops(nextShops)

        const starts = scrapingStartsRef.current
        if (Object.keys(starts).length > 0) {
          nextShops.forEach((shop: Shop) => {
            const startedAt = starts[shop.id]
            if (!startedAt) return
            const updatedAt = parseUpdatedAt(shop.updated_at)
            if (updatedAt && updatedAt >= startedAt - 1000) {
              toast.success(`店铺 ${shop.name} 抓取完成，共 ${shop.product_count || 0} 个商品`)
              delete starts[shop.id]
            }
          })
        }
      }
    } catch (error) {
      toast.error('获取店铺列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchShops()
    const interval = setInterval(fetchShops, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleAddShop = async () => {
    if (!newShopId.trim()) {
      toast.error('请输入店铺 ID')
      return
    }

    try {
      const res = await fetch(`${API_BASE}/shops`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shop_id: newShopId })
      })
      const data = await res.json()
      if (data.success) {
        toast.success('店铺添加成功')
        setNewShopId('')
        setShowAddModal(false)
        fetchShops()
      } else {
        toast.error(data.error || '添加失败')
      }
    } catch (error) {
      toast.error('添加店铺失败')
    }
  }

  const handleDeleteShop = async (id: number) => {
    if (!confirm('确定要删除这个店铺吗？')) return

    try {
      const res = await fetch(`${API_BASE}/shops/${id}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.success) {
        toast.success('店铺已删除')
        fetchShops()
      } else {
        toast.error(data.error || '删除失败')
      }
    } catch (error) {
      toast.error('删除店铺失败')
    }
  }

  const handleScrapeShop = async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/shops/${id}/scrape`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        toast.success('抓取任务已启动')
        scrapingStartsRef.current[id] = Date.now()
      } else {
        toast.error(data.error || '启动抓取失败')
      }
    } catch (error) {
      toast.error('启动抓取失败')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">店铺管理</h2>
          <p className="text-gray-500">管理你的微店店铺，抓取商品数据</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchShops}
            className="flex items-center gap-2 px-4 py-2 text-gray-600 bg-white border rounded-lg hover:bg-gray-50"
          >
            <RefreshCw size={18} />
            刷新
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700"
          >
            <Plus size={18} />
            添加店铺
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : shops.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border">
          <p className="text-gray-500">暂无店铺，请添加微店店铺</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {shops.map((shop) => (
            <div key={shop.id} className="bg-white rounded-lg border p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-gray-800">{shop.name}</h3>
                  <p className="text-sm text-gray-500">ID: {shop.shop_id}</p>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => handleScrapeShop(shop.id)}
                    className="p-2 text-blue-600 rounded-lg hover:bg-blue-50"
                    title="抓取商品"
                  >
                    <Download size={18} />
                  </button>
                  <button
                    onClick={() => handleDeleteShop(shop.id)}
                    className="p-2 text-red-600 rounded-lg hover:bg-red-50"
                    title="删除"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t flex justify-between text-sm">
                <span className="text-gray-500">商品数量</span>
                <span className="font-medium text-gray-800">{shop.product_count || 0}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 添加店铺弹窗 */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold mb-4">添加微店店铺</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  店铺 ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={newShopId}
                  onChange={(e) => setNewShopId(e.target.value)}
                  placeholder="例如: 1713062461"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <p className="mt-1 text-xs text-gray-500">
                  微店店铺 ID，可从店铺 URL 中获取
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                取消
              </button>
              <button
                onClick={handleAddShop}
                className="px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700"
              >
                添加
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
