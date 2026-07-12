import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '服务条款 · DeepAlpha',
  description: 'DeepAlpha 缠论与投研平台服务条款',
}

const UPDATED = '2025 年 7 月 12 日'
const CONTACT = 'zfleo.sg@gmail.com'

export default function TermsPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回首页
        </Link>

        <h1 className="mt-6 text-3xl font-bold tracking-tight">服务条款</h1>
        <p className="mt-2 text-sm text-muted-foreground">最后更新：{UPDATED}</p>

        <div className="mt-10 space-y-8 text-[15px] leading-7">
          <section>
            <p>
              欢迎使用 DeepAlpha（“本平台”“我们”）。本平台提供缠论技术分析等美股投研工具，
              包含网页端与 iOS 应用。使用本平台前，请仔细阅读本服务条款。使用本平台即表示
              你同意受本条款约束；若不同意，请勿使用。
            </p>
          </section>

          <Section title="一、重要免责声明（请务必阅读）">
            <p className="rounded-lg border border-border bg-muted/40 p-4 text-foreground">
              本平台提供的所有内容，包括缠论结构识别（分型、笔、线段、中枢、背驰）、买卖点标注、
              操作倾向及 AI 生成的分析，<strong>均由算法自动生成，仅供技术研究与学习参考，
              不构成任何投资建议、财务建议或买卖任何证券的要约或招揽。</strong>
              过往表现不代表未来收益。证券投资存在风险，可能导致本金损失。
              你应对自己的投资决策独立负责，并在必要时咨询持牌专业人士。
            </p>
          </Section>

          <Section title="二、账号">
            <ul className="list-disc space-y-2 pl-5">
              <li>你需提供真实、准确的信息注册账号，并对账号下的活动负责。</li>
              <li>请妥善保管登录凭证；如发现未经授权的使用，请及时联系我们。</li>
              <li>你可随时在 iOS 应用「我的 → 删除账号」中删除账号。</li>
            </ul>
          </Section>

          <Section title="三、可接受使用">
            <p>你同意不将本平台用于任何非法用途，且不得：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>试图未经授权访问系统、干扰或破坏服务；</li>
              <li>以自动化手段过度抓取、逆向工程或滥用接口；</li>
              <li>将本平台内容转售、二次分发或冒充官方来源。</li>
            </ul>
          </Section>

          <Section title="四、数据来源与准确性">
            <p>
              本平台的行情与财务数据来自第三方数据源，我们尽力保证其可用性，但不对数据的
              准确性、完整性或及时性作出保证。数据可能存在延迟、错漏或中断。
            </p>
          </Section>

          <Section title="五、知识产权">
            <p>
              本平台的软件、界面、算法实现及相关内容归我们或相应权利人所有，受法律保护。
              未经许可，不得复制、修改或用于商业用途。
            </p>
          </Section>

          <Section title="六、责任限制">
            <p>
              在适用法律允许的最大范围内，对于因使用或无法使用本平台、或依据本平台内容作出的
              任何决策而导致的直接、间接、偶发或后果性损失（包括但不限于投资损失、利润损失、
              数据丢失），我们不承担责任。本平台按“现状”与“现有”基础提供，不作任何明示或默示担保。
            </p>
          </Section>

          <Section title="七、服务变更与终止">
            <p>
              我们可能随时调整、暂停或终止部分或全部服务，恕不另行个别通知。若你违反本条款，
              我们有权暂停或终止你的账号。
            </p>
          </Section>

          <Section title="八、条款更新">
            <p>我们可能不时更新本条款，更新后将在本页标注“最后更新”日期。继续使用即视为接受更新。</p>
          </Section>

          <Section title="九、联系我们">
            <p>
              如对本条款有任何疑问，请联系：
              <a href={`mailto:${CONTACT}`} className="text-primary underline underline-offset-4">
                {' '}{CONTACT}
              </a>
            </p>
          </Section>

          <p className="border-t border-border pt-6 text-sm text-muted-foreground">
            另见我们的{' '}
            <Link href="/privacy" className="text-primary underline underline-offset-4">
              隐私政策
            </Link>
            。
          </p>
        </div>
      </div>
    </main>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="mt-3 text-muted-foreground">{children}</div>
    </section>
  )
}
