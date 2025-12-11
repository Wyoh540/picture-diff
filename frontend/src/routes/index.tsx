import { createFileRoute } from '@tanstack/react-router'
import { useMutation } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { Upload, ScanSearch, Loader2, AlertCircle, Image } from 'lucide-react'
import { detectDifferencesApiV1DiffDetectPostMutation } from '../client/@tanstack/react-query.gen'
import type { DiffResponse } from '../client/types.gen'

export const Route = createFileRoute('/')({ component: App })

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [result, setResult] = useState<DiffResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const mutation = useMutation({
    ...detectDifferencesApiV1DiffDetectPostMutation(),
    onSuccess: (data) => {
      setResult(data)
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setResult(null)
    }
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file && file.type.startsWith('image/')) {
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setResult(null)
    }
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  const handleDetect = () => {
    if (!selectedFile) return
    mutation.mutate({
      body: {
        file: selectedFile,
      },
    })
  }

  const handleReset = () => {
    setSelectedFile(null)
    setPreviewUrl(null)
    setResult(null)
    mutation.reset()
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900">
      {/* Hero 区域 */}
      <section className="relative py-12 px-6 text-center overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-purple-500/10"></div>
        <div className="relative max-w-4xl mx-auto">
          <div className="flex items-center justify-center gap-4 mb-4">
            <ScanSearch className="w-16 h-16 text-cyan-400" />
            <h1 className="text-4xl md:text-5xl font-bold text-white">
              图片差异检测
            </h1>
          </div>
          <p className="text-lg text-gray-300 mb-2">
            上传游戏截图，自动检测并标记两张图片之间的差异区域
          </p>
          <p className="text-sm text-gray-400">
            支持上下拼接的游戏截图，系统会自动分割并对比
          </p>
        </div>
      </section>

      {/* 上传区域 */}
      <section className="py-8 px-6 max-w-4xl mx-auto">
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${
            previewUrl
              ? 'border-cyan-500 bg-cyan-500/10'
              : 'border-gray-600 hover:border-cyan-500/50 bg-slate-800/50'
          }`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
            id="file-upload"
          />

          {previewUrl ? (
            <div className="space-y-4">
              <div className="flex justify-center">
                <img
                  src={previewUrl}
                  alt="预览"
                  className="max-h-64 rounded-lg shadow-lg"
                />
              </div>
              <p className="text-gray-300">{selectedFile?.name}</p>
              <div className="flex justify-center gap-4">
                <button
                  onClick={handleDetect}
                  disabled={mutation.isPending}
                  className="px-6 py-3 bg-cyan-500 hover:bg-cyan-600 disabled:bg-cyan-500/50 text-white font-semibold rounded-lg transition-colors shadow-lg shadow-cyan-500/30 flex items-center gap-2"
                >
                  {mutation.isPending ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      检测中...
                    </>
                  ) : (
                    <>
                      <ScanSearch className="w-5 h-5" />
                      开始检测
                    </>
                  )}
                </button>
                <button
                  onClick={handleReset}
                  disabled={mutation.isPending}
                  className="px-6 py-3 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-600/50 text-white font-semibold rounded-lg transition-colors"
                >
                  重新选择
                </button>
              </div>
            </div>
          ) : (
            <label htmlFor="file-upload" className="cursor-pointer block">
              <Upload className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-xl text-gray-300 mb-2">
                拖拽图片到此处或点击上传
              </p>
              <p className="text-sm text-gray-500">
                支持 JPG、PNG 等常见图片格式
              </p>
            </label>
          )}
        </div>

        {/* 错误提示 */}
        {mutation.isError && (
          <div className="mt-4 p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-red-400 flex-shrink-0" />
            <div>
              <p className="text-red-400 font-medium">检测失败</p>
              <p className="text-red-300 text-sm">
                {mutation.error?.message || '请检查图片格式是否正确，或稍后重试'}
              </p>
            </div>
          </div>
        )}
      </section>

      {/* 结果展示区域 */}
      {result && (
        <section className="py-8 px-6 max-w-6xl mx-auto">
          <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                <Image className="w-6 h-6 text-cyan-400" />
                检测结果
              </h2>
              <div className="bg-cyan-500/20 px-4 py-2 rounded-lg">
                <span className="text-cyan-400 font-semibold">
                  发现 {result.difference_count} 处差异
                </span>
              </div>
            </div>

            {/* 差异区域信息 */}
            {result.differences && result.differences.length > 0 && (
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-300 mb-3">
                  差异区域详情
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                  {result.differences.map((diff) => (
                    <div
                      key={diff.index}
                      className="bg-slate-700/50 rounded-lg p-3 text-center"
                    >
                      <div className="text-cyan-400 font-bold mb-1">
                        #{diff.index}
                      </div>
                      <div className="text-xs text-gray-400">
                        位置: ({diff.x}, {diff.y})
                      </div>
                      <div className="text-xs text-gray-400">
                        尺寸: {diff.width}×{diff.height}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 结果图片展示 */}
            <div className="space-y-6">
              {/* 拼接标记图 */}
              {result.marked_image_base64 && (
                <div>
                  <h3 className="text-lg font-medium text-gray-300 mb-3">
                    对比标记图
                  </h3>
                  <div className="flex justify-center">
                    <img
                      src={`data:image/png;base64,${result.marked_image_base64}`}
                      alt="差异标记图"
                      className="max-w-full rounded-lg shadow-lg border border-slate-600"
                    />
                  </div>
                </div>
              )}

              {/* 热力图 */}
              {result.heatmap_base64 && (
                <div>
                  <h3 className="text-lg font-medium text-gray-300 mb-3">
                    差异热力图
                  </h3>
                  <div className="flex justify-center">
                    <img
                      src={`data:image/png;base64,${result.heatmap_base64}`}
                      alt="差异热力图"
                      className="max-w-full rounded-lg shadow-lg border border-slate-600"
                    />
                  </div>
                </div>
              )}

              {/* 单独标记的图片 */}
              {(result.image1_base64 || result.image2_base64) && (
                <div>
                  <h3 className="text-lg font-medium text-gray-300 mb-3">
                    单独标记图
                  </h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    {result.image1_base64 && (
                      <div>
                        <p className="text-sm text-gray-400 mb-2 text-center">
                          图片 1
                        </p>
                        <img
                          src={`data:image/png;base64,${result.image1_base64}`}
                          alt="图片1标记"
                          className="w-full rounded-lg shadow-lg border border-slate-600"
                        />
                      </div>
                    )}
                    {result.image2_base64 && (
                      <div>
                        <p className="text-sm text-gray-400 mb-2 text-center">
                          图片 2
                        </p>
                        <img
                          src={`data:image/png;base64,${result.image2_base64}`}
                          alt="图片2标记"
                          className="w-full rounded-lg shadow-lg border border-slate-600"
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
