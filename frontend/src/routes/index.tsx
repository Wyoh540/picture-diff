import { createFileRoute } from '@tanstack/react-router'
import { useMutation } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { Upload, ScanSearch, Loader2, AlertCircle, Image } from 'lucide-react'
import { detectDifferencesApiV1DiffDetectPostMutation } from '../client/@tanstack/react-query.gen'
import type { DiffResponse } from '../client/types.gen'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'

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
    <div className="min-h-screen bg-background">
      {/* Hero 区域 */}
      <section className="relative py-12 px-6 text-center overflow-hidden border-b">
        <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-primary/10 to-primary/5" />
        <div className="relative max-w-4xl mx-auto">
          <div className="flex items-center justify-center gap-4 mb-4">
            <ScanSearch className="size-16 text-primary" />
            <h1 className="text-4xl md:text-5xl font-bold">图片差异检测</h1>
          </div>
          <p className="text-lg text-muted-foreground mb-2">
            上传游戏截图，自动检测并标记两张图片之间的差异区域
          </p>
          <p className="text-sm text-muted-foreground">
            支持上下拼接的游戏截图，系统会自动分割并对比
          </p>
        </div>
      </section>

      {/* 上传区域 */}
      <section className="py-8 px-6 max-w-4xl mx-auto">
        <Card>
          <CardContent className="pt-6">
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 cursor-pointer ${
                previewUrl
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-primary/50 bg-muted/30'
              }`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onClick={() => !previewUrl && fileInputRef.current?.click()}
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
                  <p className="text-muted-foreground">{selectedFile?.name}</p>
                  <div className="flex justify-center gap-4">
                    <Button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDetect()
                      }}
                      disabled={mutation.isPending}
                      size="lg"
                    >
                      {mutation.isPending ? (
                        <>
                          <Loader2 className="size-5 animate-spin" />
                          检测中...
                        </>
                      ) : (
                        <>
                          <ScanSearch className="size-5" />
                          开始检测
                        </>
                      )}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleReset()
                      }}
                      disabled={mutation.isPending}
                      size="lg"
                    >
                      重新选择
                    </Button>
                  </div>
                </div>
              ) : (
                <label htmlFor="file-upload" className="cursor-pointer block">
                  <Upload className="size-16 text-muted-foreground mx-auto mb-4" />
                  <p className="text-xl mb-2">拖拽图片到此处或点击上传</p>
                  <p className="text-sm text-muted-foreground">
                    支持 JPG、PNG 等常见图片格式
                  </p>
                </label>
              )}
            </div>

            {/* 错误提示 */}
            {mutation.isError && (
              <Alert variant="destructive" className="mt-4">
                <AlertCircle className="size-4" />
                <AlertTitle>检测失败</AlertTitle>
                <AlertDescription>
                  {mutation.error?.message || '请检查图片格式是否正确，或稍后重试'}
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      </section>

      {/* 结果展示区域 */}
      {result && (
        <section className="py-8 px-6 max-w-6xl mx-auto">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Image className="size-6 text-primary" />
                检测结果
              </CardTitle>
              <Badge variant="secondary" className="text-base px-4 py-1.5">
                发现 {result.difference_count} 处差异
              </Badge>
            </CardHeader>
            <CardContent>
              {/* 差异区域信息 */}
              {result.differences && result.differences.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-lg font-medium mb-3">差异区域详情</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                    {result.differences.map((diff) => (
                      <Card key={diff.index} className="py-3">
                        <CardContent className="text-center p-0">
                          <div className="text-primary font-bold mb-1">
                            #{diff.index}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            位置: ({diff.x}, {diff.y})
                          </div>
                          <div className="text-xs text-muted-foreground">
                            尺寸: {diff.width}×{diff.height}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* 结果图片展示 */}
              <div className="space-y-6">
                {/* 拼接标记图 */}
                {result.marked_image_base64 && (
                  <div>
                    <h3 className="text-lg font-medium mb-3">对比标记图</h3>
                    <div className="flex justify-center">
                      <img
                        src={`data:image/png;base64,${result.marked_image_base64}`}
                        alt="差异标记图"
                        className="max-w-full rounded-lg shadow-lg border"
                      />
                    </div>
                  </div>
                )}

                {/* 热力图 */}
                {result.heatmap_base64 && (
                  <div>
                    <h3 className="text-lg font-medium mb-3">差异热力图</h3>
                    <div className="flex justify-center">
                      <img
                        src={`data:image/png;base64,${result.heatmap_base64}`}
                        alt="差异热力图"
                        className="max-w-full rounded-lg shadow-lg border"
                      />
                    </div>
                  </div>
                )}

                {/* 单独标记的图片 */}
                {(result.image1_base64 || result.image2_base64) && (
                  <div>
                    <h3 className="text-lg font-medium mb-3">单独标记图</h3>
                    <div className="grid md:grid-cols-2 gap-4">
                      {result.image1_base64 && (
                        <div>
                          <p className="text-sm text-muted-foreground mb-2 text-center">
                            图片 1
                          </p>
                          <img
                            src={`data:image/png;base64,${result.image1_base64}`}
                            alt="图片1标记"
                            className="w-full rounded-lg shadow-lg border"
                          />
                        </div>
                      )}
                      {result.image2_base64 && (
                        <div>
                          <p className="text-sm text-muted-foreground mb-2 text-center">
                            图片 2
                          </p>
                          <img
                            src={`data:image/png;base64,${result.image2_base64}`}
                            alt="图片2标记"
                            className="w-full rounded-lg shadow-lg border"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  )
}
