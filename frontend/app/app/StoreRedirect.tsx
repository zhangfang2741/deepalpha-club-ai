'use client'

import { useEffect, useState } from 'react'

/** App Store 商品页链接。App 未上架时留空，页面会显示「即将上架」。 */
export const APP_STORE_ID = '6806500280'

/**
 * iOS 设备自动跳转 App Store。
 *
 * 跳转刻意放在客户端而不是服务端重定向：这个页面会被 Cloudflare 缓存，
 * 服务端按 UA 分流容易被边缘缓存固化成对所有人都跳转（或都不跳）。
 */
export default function StoreRedirect() {
  const [redirecting, setRedirecting] = useState(false)

  useEffect(() => {
    if (!APP_STORE_ID) return

    const ua = navigator.userAgent
    // iPadOS 13+ 的 Safari 默认伪装成 macOS，靠触摸点数补判
    const isIOS =
      /iPhone|iPad|iPod/.test(ua) ||
      (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)

    if (isIOS) {
      setRedirecting(true)
      window.location.replace(`https://apps.apple.com/app/id${APP_STORE_ID}`)
    }
  }, [])

  if (redirecting) {
    return <p className="text-sm text-muted-foreground">正在打开 App Store…</p>
  }

  if (!APP_STORE_ID) {
    return (
      <div className="rounded-lg border border-border bg-muted/40 p-4">
        <p className="text-sm">
          iOS 版正在 App Store 审核中，即将上线。可先在网页端使用，或来信留个邮箱，
          上线后我们通知你。
        </p>
      </div>
    )
  }

  return (
    <a
      href={`https://apps.apple.com/app/id${APP_STORE_ID}`}
      className="inline-flex items-center rounded-lg bg-primary px-5 py-3 text-sm font-medium text-primary-foreground"
    >
      在 App Store 下载
    </a>
  )
}
