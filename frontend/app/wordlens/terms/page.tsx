import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '服务条款 · 鹦鹉背单词',
  description: '鹦鹉背单词（WordLens）iOS 应用服务条款',
}

const UPDATED = '2026 年 8 月 15 日'
const CONTACT = 'zfleo.sg@gmail.com'

export default function WordLensTermsPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="mt-6 text-3xl font-bold tracking-tight">服务条款</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          适用于「鹦鹉背单词」iOS 应用 · 最后更新：{UPDATED}
        </p>

        <div className="mt-10 space-y-8 text-[15px] leading-7">
          <section>
            <p>
              欢迎使用「鹦鹉背单词」（WordLens，以下称“本应用”）。本条款是你与本应用
              开发者之间就使用本应用达成的协议。下载、注册或使用本应用，即表示你已阅读、
              理解并同意本条款。若你不同意，请停止使用并删除本应用。
            </p>
          </section>

          <Section title="一、服务内容">
            <p>
              本应用提供英语单词学习工具，主要功能包括：通过拍照识别图片中的英语单词、
              自动生成音标与中文释义、基于间隔重复算法安排复习、单词发音朗读，
              以及语音听写练习。
            </p>
          </Section>

          <Section title="二、关于识别与释义准确性的免责声明">
            <p>
              本应用的单词识别、音标标注、中文释义、词源与例句生成，
              <strong>均由人工智能模型自动完成，可能出现错误、遗漏或不准确之处</strong>。
              语音听写的判定同样依赖语音识别技术，可能因口音、环境噪音或网络状况产生误判。
            </p>
            <p className="mt-3">
              本应用是<strong>学习辅助工具，不能替代词典、教材或教师</strong>。
              涉及考试、翻译、学术写作等对准确性要求较高的场景，请以权威词典为准。
              我们不对因依赖本应用内容而导致的任何后果承担责任。
            </p>
          </Section>

          <Section title="三、账号">
            <ul className="list-disc space-y-2 pl-5">
              <li>你需提供有效的电子邮箱或手机号注册账号，并对账号下的一切活动负责。</li>
              <li>请妥善保管密码。如发现账号被盗用，请立即修改密码并联系我们。</li>
              <li>
                你可随时在应用内「设置 → 删除账号」自助删除账号。删除后全部数据将被
                永久清除且不可恢复，详见
                <Link href="/wordlens/privacy" className="text-primary underline underline-offset-4">
                  {' '}隐私政策
                </Link>
                。
              </li>
              <li>若你未满 18 周岁，请在监护人知情并同意的情况下使用本应用。</li>
            </ul>
          </Section>

          <Section title="四、可接受使用">
            <p>使用本应用时，你同意不进行以下行为：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>上传含有违法、暴力、色情、侵犯他人隐私或其他不当内容的图片。</li>
              <li>
                上传你不享有合法使用权的受版权保护材料。你需对上传内容的合法性自行负责。
              </li>
              <li>通过自动化脚本、爬虫等方式批量调用服务，或以其他方式滥用、干扰服务运行。</li>
              <li>尝试逆向工程、破解或未经授权访问本应用的服务端接口。</li>
              <li>将本应用用于任何违反所在地法律法规的用途。</li>
            </ul>
            <p className="mt-3">
              我们保留对滥用行为进行限流、暂停或终止服务的权利。
            </p>
          </Section>

          <Section title="五、知识产权">
            <p>
              本应用的软件、界面设计、图标与文案等内容的知识产权归开发者所有。
              你通过本应用创建的生词库与学习记录归你所有；你授予我们为提供服务
              所必需的处理与存储许可，该许可在你删除账号时终止。
            </p>
          </Section>

          <Section title="六、服务可用性与第三方依赖">
            <p>
              本应用依赖第三方服务（如人工智能模型、语音合成、云基础设施）运行。
              这些服务可能因维护、故障、政策调整或不可抗力而中断，
              进而影响识别、发音等功能的可用性。
            </p>
            <p className="mt-3">
              本应用按“现状”提供，我们不对服务的<strong>持续可用性、无中断或无错误
              </strong>作出保证。我们可能不时调整、新增或下线部分功能。
            </p>
          </Section>

          <Section title="七、责任限制">
            <p>
              在适用法律允许的最大范围内，对于因使用或无法使用本应用而产生的任何间接、
              附带、特殊或后果性损失（包括但不限于学习数据丢失、考试成绩不理想、
              时间损失），我们不承担责任。
            </p>
            <p className="mt-3">
              我们建议你不要将本应用作为学习资料的唯一存放处，重要内容请自行留存备份。
            </p>
          </Section>

          <Section title="八、费用">
            <p>
              本应用当前免费提供。若未来推出付费功能或订阅，我们会提前在应用内明确告知
              价格与条款，付费与否由你自主选择，不影响你已有数据的访问与导出。
            </p>
          </Section>

          <Section title="九、服务变更与终止">
            <p>
              我们可能变更、暂停或终止本应用的全部或部分服务。若计划永久停止服务，
              我们会尽合理努力提前通知，并为你保留一段时间以便删除或导出数据。
              你也可以随时停止使用并删除账号。
            </p>
          </Section>

          <Section title="十、条款更新">
            <p>
              我们可能不时更新本条款。重大变更会更新本页的“最后更新”日期并在应用内提示。
              变更生效后你继续使用本应用，即视为接受更新后的条款。
            </p>
          </Section>

          <Section title="十一、联系我们">
            <p>
              如对本条款有任何疑问，请联系：
              <a href={`mailto:${CONTACT}`} className="text-primary underline underline-offset-4">
                {' '}{CONTACT}
              </a>
            </p>
          </Section>

          <p className="border-t border-border pt-6 text-sm text-muted-foreground">
            另见「鹦鹉背单词」的{' '}
            <Link href="/wordlens/privacy" className="text-primary underline underline-offset-4">
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
