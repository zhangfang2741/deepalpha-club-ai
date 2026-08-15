import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '隐私政策 · 鹦鹉背单词',
  description: '鹦鹉背单词（WordLens）iOS 应用隐私政策',
}

const UPDATED = '2026 年 8 月 15 日'
const CONTACT = 'zfleo.sg@gmail.com'

export default function WordLensPrivacyPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回首页
        </Link>

        <h1 className="mt-6 text-3xl font-bold tracking-tight">隐私政策</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          适用于「鹦鹉背单词」iOS 应用 · 最后更新：{UPDATED}
        </p>

        <div className="mt-10 space-y-8 text-[15px] leading-7">
          <section>
            <p>
              「鹦鹉背单词」（WordLens，以下称“本应用”“我们”）是一款英语单词学习工具：
              你拍下含英语单词的书页或文档，应用识别出其中的生词并配上音标、释义与例句，
              再通过间隔重复帮你复习。本政策说明本应用收集哪些信息、如何使用、与谁共享，
              以及你享有的权利。使用本应用即表示你已阅读并同意本政策。
            </p>
            <p className="mt-3">
              本政策仅适用于「鹦鹉背单词」iOS 应用。DeepAlpha 投研平台另有
              <Link href="/privacy" className="text-primary underline underline-offset-4">
                {' '}独立的隐私政策
              </Link>
              ，两者账号体系互相独立、数据互不相通。
            </p>
          </section>

          <Section title="一、我们收集并保存的信息">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong>账号信息：</strong>你注册时填写的电子邮箱，以及经 bcrypt
                单向哈希处理后的密码。我们<strong>不保存也无法还原</strong>你的明文密码。
              </li>
              <li>
                <strong>学习数据：</strong>你加入生词库的单词，及其音标、词性、中文释义、
                词源与例句；每个单词的复习状态与间隔重复进度；你的复习评分历史；
                你自建的单词歌单及其排序。
              </li>
              <li>
                <strong>偏好设置：</strong>发音口音（英音/美音）、语速、是否自动发音、
                学习模式等。这些仅保存在你的设备本地（iOS UserDefaults），不上传服务器。
              </li>
            </ul>
          </Section>

          <Section title="二、我们不保存的信息">
            <p>
              以下数据在功能流程中会被<strong>临时处理但不落地存储</strong>，请特别留意：
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong>你拍摄或选择的图片：</strong>图片仅在识别过程中被传输和处理，
                <strong>不会写入我们的数据库，也不会保存到任何磁盘或对象存储</strong>。
                识别请求结束后，图片即从内存中释放。我们不保留任何图片副本。
              </li>
              <li>
                <strong>你的语音录音：</strong>语音听写功能的音频由 iOS 系统的语音识别
                服务处理（见第三节），<strong>完全不经过我们的服务器</strong>，我们既接触
                不到也不保存。
              </li>
            </ul>
            <p className="mt-3">
              我们<strong>不收集</strong>：你的位置、通讯录、日历、健康数据、设备标识符
              （IDFA/IDFV）、相册中你未主动选择的其他照片。本应用<strong>不含任何广告
              SDK，不做跨应用或跨网站的用户追踪</strong>，因此也不会向你弹出
              App 追踪透明度（ATT）授权请求。
            </p>
          </Section>

          <Section title="三、第三方服务">
            <p>为实现核心功能，以下数据会被发送给相应的服务提供商，且仅限完成该功能所需范围：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                <strong>Google（Gemini 模型）—— 图片识别：</strong>你拍摄的图片会被发送至
                Google 的 Gemini 视觉模型，用于识别其中的英语单词并生成音标、释义与例句。
                我们发送的仅有图片本身，<strong>不附带你的邮箱、账号 ID 或任何身份信息</strong>，
                Google 无法将该图片关联到你个人。其数据处理遵循 Google 的隐私政策。
              </li>
              <li>
                <strong>Apple —— 语音识别：</strong>使用语音听写时，你说出的音频由 iOS 的
                <code className="mx-1 rounded bg-muted px-1 py-0.5 text-[13px]">SFSpeechRecognizer</code>
                处理。为保证识别准确率，本应用<strong>使用 Apple 的云端语音识别服务</strong>，
                这意味着音频会被发送至 Apple 的服务器进行转写。该过程由 iOS 系统完成，
                受 Apple 的隐私政策约束，我们不接收也不存储这些音频。
              </li>
              <li>
                <strong>MiniMax —— 单词发音：</strong>朗读单词时，我们会将<strong>单词文本
                </strong>（例如 “resilient”）发送至语音合成服务以生成音频。发送内容不含
                你的任何身份信息。
              </li>
              <li>
                <strong>基础设施：</strong>服务器、数据库与缓存由 Railway 提供，
                域名解析与传输加速由 Cloudflare 提供。
              </li>
            </ul>
            <p className="mt-3">
              我们<strong>不会出售你的个人信息</strong>，也不会将其用于广告投放。
            </p>
          </Section>

          <Section title="四、设备权限说明">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong>相机：</strong>仅在你主动点击「拍照」时使用，用于拍摄含英语单词的
                书页或文档。
              </li>
              <li>
                <strong>麦克风：</strong>仅在你主动开启语音听写并点击麦克风按钮时使用，
                用于录下你说出的单词。
              </li>
              <li>
                <strong>语音识别：</strong>用于把你说出的单词转写为文字，以判定听写是否正确。
              </li>
            </ul>
            <p className="mt-3">
              以上权限均可在 iOS「设置 → 隐私与安全性」中随时撤销。撤销后对应功能不可用，
              但不影响其他功能的正常使用。
            </p>
          </Section>

          <Section title="五、数据存储与安全">
            <p>
              数据存储于具备访问控制与传输加密（HTTPS/TLS）的云服务中，全部网络请求均走
              加密通道。密码经 bcrypt 哈希处理后存储。登录凭证（JWT）在 iOS 端保存于系统
              Keychain，不写入普通文件或偏好设置。尽管我们采取了合理的安全措施，
              但没有任何互联网传输或存储方式能保证绝对安全。
            </p>
          </Section>

          <Section title="六、数据保留与账号删除">
            <p>
              你的账号与学习数据会一直保留，直到你主动删除账号。你可以在应用内
              <strong>「设置 → 删除账号」</strong>随时自助删除，需输入密码确认。
            </p>
            <p className="mt-3">删除后，以下数据将被<strong>立即永久清除且无法恢复</strong>：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>你的账号与登录凭证</li>
              <li>全部生词及其音标、释义、词源、例句</li>
              <li>全部复习进度与复习历史记录</li>
              <li>全部自建歌单</li>
            </ul>
            <p className="mt-3">
              我们不设“回收站”或宽限期，删除即为彻底删除。若你无法登录应用，也可通过
              下方邮箱联系我们代为删除。
            </p>
          </Section>

          <Section title="七、你的权利">
            <p>
              你有权访问、更正你的账号信息（应用内可修改密码），有权删除账号及全部数据
              （见上一节），也有权就本政策向我们提出疑问。如你位于欧洲经济区、英国或
              中国大陆等地区，你还可能享有当地法律赋予的数据可携权、限制处理权等权利，
              可通过下方邮箱与我们联系行使。
            </p>
          </Section>

          <Section title="八、未成年人">
            <p>
              本应用面向英语学习者，但<strong>不针对 13 周岁以下儿童设计，也不会有意收集
              其个人信息</strong>。若你未满 18 周岁，请在监护人知情并同意的情况下使用本应用。
              若我们发现误收集了 13 周岁以下儿童的信息，将尽快删除；监护人如发现此类情况，
              可通过下方邮箱联系我们要求删除。
            </p>
          </Section>

          <Section title="九、政策更新">
            <p>
              我们可能不时更新本政策。发生重大变更时，我们会更新本页的“最后更新”日期，
              并在应用内作出提示。
            </p>
          </Section>

          <Section title="十、联系我们">
            <p>
              如对本隐私政策有任何疑问，或需要行使上述权利，请联系：
              <a href={`mailto:${CONTACT}`} className="text-primary underline underline-offset-4">
                {' '}{CONTACT}
              </a>
            </p>
          </Section>

          <p className="border-t border-border pt-6 text-sm text-muted-foreground">
            另见「鹦鹉背单词」的{' '}
            <Link href="/wordlens/terms" className="text-primary underline underline-offset-4">
              服务条款
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
