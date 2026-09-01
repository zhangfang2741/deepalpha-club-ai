import type { Metadata } from 'next'
import Link from 'next/link'

import StoreRedirect from './StoreRedirect'

export const metadata: Metadata = {
  title: '下载 DeepAlpha 缠论 · iOS',
  description: 'DeepAlpha 缠论 iOS 应用：自动标注 K 线上的分型、笔、线段、中枢与买卖点。',
}

const CONTACT = 'zfleo.sg@gmail.com'

/**
 * App 下载中转页（`/app`）。
 *
 * App 内分享图上的二维码指向这里，而不是直接指向 App Store：二维码一旦印进
 * 用户分享出去的图里就再也改不了，中转页由我们自己控制，上架前后都能用。
 */
export default function AppDownloadPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-2xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回首页
        </Link>

        <h1 className="mt-6 text-3xl font-bold tracking-tight">DeepAlpha 缠论</h1>
        <p className="mt-3 text-[15px] leading-7 text-muted-foreground">
          把 K 线图上的缠论结构自动标出来：K 线包含处理、分型、笔、线段、中枢、背驰，
          以及一二三类买卖点，全部直接画在图上。支持美股、A 股、港股，日线与周线。
        </p>

        <div className="mt-8">
          <StoreRedirect />
        </div>

        <ul className="mt-10 space-y-3 text-[15px] leading-7">
          <li>· 自动识别缠论结构，配 MACD 副图与背驰面积比</li>
          <li>· 9 篇带图入门词条，图例术语可点开对应讲解</li>
          <li>· 图表支持缩放、平移与全屏查看</li>
        </ul>

        <p className="mt-10 rounded-lg border border-border bg-muted/40 p-4 text-sm leading-6">
          App 提供的全部内容均由算法基于公开行情数据自动生成，属于技术分析与学习材料，
          <strong>不构成任何投资建议</strong>。投资有风险，决策请自主判断。
        </p>

        <p className="mt-8 text-sm text-muted-foreground">
          有问题请联系{' '}
          <a href={`mailto:${CONTACT}`} className="text-primary underline underline-offset-4">
            {CONTACT}
          </a>
          。另见{' '}
          <Link href="/terms" className="text-primary underline underline-offset-4">
            服务条款
          </Link>{' '}
          与{' '}
          <Link href="/privacy" className="text-primary underline underline-offset-4">
            隐私政策
          </Link>
          。
        </p>
      </div>
    </main>
  )
}
