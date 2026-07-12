import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '隐私政策 · DeepAlpha',
  description: 'DeepAlpha 缠论与投研平台隐私政策',
}

const UPDATED = '2025 年 7 月 12 日'
const CONTACT = 'zfleo.sg@gmail.com'

export default function PrivacyPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回首页
        </Link>

        <h1 className="mt-6 text-3xl font-bold tracking-tight">隐私政策</h1>
        <p className="mt-2 text-sm text-muted-foreground">最后更新：{UPDATED}</p>

        <div className="mt-10 space-y-8 text-[15px] leading-7">
          <section>
            <p>
              DeepAlpha（“本平台”“我们”）提供缠论技术分析等美股投研工具，包含网页端与
              iOS 应用。我们重视你的隐私。本政策说明我们收集哪些信息、如何使用与保护，
              以及你享有的权利。使用本平台即表示你已阅读并同意本政策。
            </p>
          </section>

          <Section title="一、我们收集的信息">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong>账号信息：</strong>注册或登录时提供的电子邮箱、用户名，以及加密存储的密码
                （我们仅保存经不可逆哈希处理后的密码，无法还原明文）。
              </li>
              <li>
                <strong>Sign in with Apple：</strong>若你选择通过 Apple 登录，我们仅接收
                Apple 提供的匿名用户标识与（你授权时的）邮箱，用于创建与识别账号。
              </li>
              <li>
                <strong>使用数据：</strong>你查询的股票代码、日期范围、分析偏好等操作记录，
                以及为保障服务所需的技术日志（如请求时间、错误信息）。
              </li>
              <li>
                <strong>我们不收集：</strong>我们不采集你的通讯录、位置、相册，也不用于广告追踪。
              </li>
            </ul>
          </Section>

          <Section title="二、信息的使用">
            <ul className="list-disc space-y-2 pl-5">
              <li>提供并维护核心功能（身份认证、缠论与投研分析、会话历史）。</li>
              <li>保障账号与系统安全、防止滥用与限流。</li>
              <li>诊断故障、改进产品体验。</li>
            </ul>
          </Section>

          <Section title="三、第三方服务">
            <p>为实现功能，我们会将必要数据传输给以下服务提供商，且仅限完成相应功能所需范围：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong>行情与财务数据源</strong>（如 Financial Modeling Prep 等）：用于获取
                你所查询标的的公开市场数据。我们向其发送的是股票代码等查询参数，不含你的身份信息。
              </li>
              <li>
                <strong>大语言模型服务商</strong>（如 OpenAI、Anthropic、Google 等）：用于
                结构 GAP 等 AI 分析。相关文本可能被发送至模型服务商处理。
              </li>
              <li>
                <strong>基础设施</strong>：数据库（Supabase）、缓存（Upstash）、部署与
                CDN（Railway / Vercel / Cloudflare）用于存储与分发。
              </li>
            </ul>
            <p className="mt-3">我们不会出售你的个人信息。</p>
          </Section>

          <Section title="四、数据存储与安全">
            <p>
              数据存储于具备访问控制与传输加密（HTTPS/TLS）的云服务中。密码经哈希处理，
              登录凭证（JWT）通过安全通道传输，iOS 端保存在系统 Keychain。尽管我们采取
              合理的安全措施，但没有任何互联网传输或存储方式能保证绝对安全。
            </p>
          </Section>

          <Section title="五、你的权利与账号删除">
            <p>
              你可随时查看与更新账号资料。你有权删除账号：在 iOS 应用「我的 → 删除账号」，
              或通过下方邮箱联系我们。<strong>删除后，你的账号及关联数据将被永久移除且不可恢复。</strong>
            </p>
          </Section>

          <Section title="六、未成年人">
            <p>本平台不面向 18 周岁以下人士。若我们发现误收集了未成年人信息，将尽快删除。</p>
          </Section>

          <Section title="七、政策更新">
            <p>我们可能不时更新本政策，重大变更会在本页更新“最后更新”日期并作提示。</p>
          </Section>

          <Section title="八、联系我们">
            <p>
              如对本隐私政策有任何疑问，请联系：
              <a href={`mailto:${CONTACT}`} className="text-primary underline underline-offset-4">
                {' '}{CONTACT}
              </a>
            </p>
          </Section>

          <p className="border-t border-border pt-6 text-sm text-muted-foreground">
            另见我们的{' '}
            <Link href="/terms" className="text-primary underline underline-offset-4">
              服务条款
            </Link>
            。本平台所有分析内容仅供技术研究与学习参考，不构成投资建议。
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
