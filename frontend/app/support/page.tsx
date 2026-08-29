import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '支持与帮助 · DeepAlpha 缠论',
  description: 'DeepAlpha 缠论 iOS 应用的使用帮助、常见问题与联系方式',
}

const UPDATED = '2026 年 8 月 29 日'
const CONTACT = 'zfleo.sg@gmail.com'

export default function ChanSupportPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="mt-6 text-3xl font-bold tracking-tight">支持与帮助</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          「DeepAlpha 缠论」iOS 应用 · 最后更新：{UPDATED}
        </p>

        {/* 联系方式放最上面：来支持页的人多半是遇到问题了，别让他先读一堆 FAQ */}
        <div className="mt-10 rounded-xl border border-border bg-muted/30 p-6">
          <h2 className="text-lg font-semibold">直接联系我们</h2>
          <p className="mt-2 text-[15px] leading-7 text-muted-foreground">
            遇到问题、有功能建议，或需要帮忙处理账号，发邮件即可，通常 1–2 个工作日内回复。
          </p>
          <a
            href={`mailto:${CONTACT}?subject=${encodeURIComponent('【DeepAlpha 缠论】问题反馈')}`}
            className="mt-4 inline-block text-lg font-medium text-primary underline underline-offset-4"
          >
            {CONTACT}
          </a>
          <p className="mt-4 text-sm text-muted-foreground">
            为了更快定位问题，邮件里麻烦附上：你的注册邮箱或手机号、iPhone 型号与 iOS 版本、
            App 版本号（在「我的 → 版本」可以看到）、出问题的股票代码与时间范围，以及截图。
          </p>
        </div>

        <div className="mt-10 rounded-xl border border-amber-500/30 bg-amber-500/5 p-6">
          <h2 className="text-lg font-semibold">重要提示</h2>
          <p className="mt-2 text-[15px] leading-7 text-muted-foreground">
            本 App 提供的全部内容均由算法基于公开行情数据自动生成，属于技术分析与学习材料，
            <strong className="text-foreground">不构成任何投资建议、要约或承诺</strong>。
            缠论是一套描述走势结构的分析方法，其识别结果会随数据更新而变化，不具备预测能力。
            投资有风险，所有决策请自主判断并自行承担后果。
          </p>
        </div>

        <div className="mt-12 space-y-8 text-[15px] leading-7">
          <Section title="「一买」「二卖」是让我买入或卖出吗？">
            <p>
              不是。「买卖点」是<strong>缠论这套理论对走势结构位置的固定命名</strong>，
              和「分型」「中枢」一样属于术语，描述的是价格结构走到了什么位置，
              不是操作指令，也不代表我们建议你做任何交易。
            </p>
            <p className="mt-3">
              App 里所有措辞都刻意避开了操作动词：「形态分析」那一栏给出的是
              「技术面偏强 / 偏弱 / 多空僵持」这类对结构的客观描述，以及得出它的逐条依据。
              技术上的「买点」不等于投资上的「值得买」——是否值得买，还要结合基本面、
              估值、盈利预期和市场环境，由你自己判断。
            </p>
          </Section>

          <Section title="「形态分析」里的倾向是怎么算出来的？">
            <p>
              把六个维度各折算成一个带正负号的分数再加总：最近的买卖点信号、最后一笔的方向、
              线段方向、当前价相对最近中枢的位置、是否出现背驰、以及量价配合。
              正数偏多、负数偏空，净值接近零就是「多空僵持」。
            </p>
            <p className="mt-3">
              「依据」列表的第一条会告诉你这次有几项偏多、几项偏空。
              因为结论是<strong>加权净值</strong>，所以下面单独某一条依据的方向可能和
              总结论相反——这是正常的，不是矛盾。
            </p>
          </Section>

          <Section title="为什么图上有些线是虚线？">
            <p>
              虚线表示<strong>该结构尚未被后续 K 线确认</strong>。缠论的分型、笔、线段、中枢
              都要等后面的走势走出来才能最终成立，最右侧那部分永远处在「可能还会变」的状态：
              分型可能随包含处理移动或消失，笔的端点可能被突破而延伸，中枢可能仍在扩张。
            </p>
            <p className="mt-3">
              我们把这种右侧的不确定性显式标出来，而不是画成实线让它看起来已成定局。
              落在未确认笔上的买卖点会标注「未确认」，属于左侧预判，需要后续 K 线验证。
            </p>
          </Section>

          <Section title="每天能免费分析几次？额度怎么算？">
            <p>
              免费用户每天可以分析 <strong>3 支不同的股票</strong>。计量单位是「不同标的」——
              同一支股票当天反复分析（换周期、改日期）<strong>不重复扣次数</strong>，
              额度用完之后，当天已经分析过的股票<strong>仍然可以继续查看</strong>，
              只是不能再分析新的标的。
            </p>
            <p className="mt-3">额度按自然日重置。</p>
          </Section>

          <Section title="股票代码怎么输入？">
            <p>先在左上角选市场，再按各市场习惯输入即可：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li><strong>美股</strong>：字母代码，如 <code>AAPL</code></li>
              <li><strong>A 股</strong>：6 位数字，如 <code>600519</code></li>
              <li><strong>港股</strong>：4–5 位数字，如 <code>0700</code></li>
            </ul>
            <p className="mt-3">
              市场需要你显式选择，我们不靠代码形态去猜——4 到 6 位数字在 A 股和港股之间
              存在歧义，猜错了你没有办法纠正。切换市场时代码框会清空，因为格式本来就不通用。
            </p>
          </Section>

          <Section title="订阅、试用与取消">
            <p>
              「DeepAlpha Pro 月度会员」解除每日次数限制，按月自动续订，
              具体价格以 App 内付费墙显示为准（会按你 App Store 账号所在地区的货币显示）。
              首次订阅含免费试用期，试用结束后才开始扣费。
            </p>
            <p className="mt-3">
              取消订阅在<strong>「iPhone 设置 → Apple 账户 → 订阅」</strong>里操作，
              需要在当前订阅周期结束前至少 24 小时取消，否则会自动续订下一期。
              取消后当期剩余时间仍可正常使用，到期后回到每日 3 次的免费额度。
            </p>
            <p className="mt-3">
              换了设备或重装 App，在付费墙或「我的」页点<strong>「恢复购买」</strong>即可恢复会员身份，
              不需要重新付费。
            </p>
          </Section>

          <Section title="分析结果和我用的其他软件不一样？">
            <p>
              缠论在实现细节上没有唯一标准，不同软件对<strong>笔的成立条件</strong>
              （两个分型之间至少要间隔几根 K 线）、线段的划分方式、背驰的判定口径
              都可能采用不同参数，结果自然会有差异。
            </p>
            <p className="mt-3">
              本 App 采用的是「新笔」标准，并使用 MACD 面积比来判断背驰，
              面积比数值直接标在每个买卖点上，你可以自己核对。
              「学习」页里有 9 篇词条解释每个概念的具体定义。
            </p>
          </Section>

          <Section title="拉不到数据 / 提示分析失败">
            <p>依次检查：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>代码格式和所选市场是否匹配（见上文）</li>
              <li>该标的在所选时间范围内是否有足够的交易数据——新股、长期停牌、已退市的标的可能拿不到</li>
              <li>时间范围是否太短。缠论需要足够多的 K 线才能形成结构，建议至少留半年以上</li>
              <li>网络是否正常，可以切换 Wi-Fi 与蜂窝数据试试</li>
            </ul>
            <p className="mt-3">
              如果换了几个标的都失败，可能是我们的服务出了问题，欢迎直接发邮件告诉我们。
            </p>
          </Section>

          <Section title="图表怎么操作？">
            <p>
              图表可以横向滑动平移、双指缩放，点右上角的图标可以<strong>全屏横屏</strong>查看更多 K 线。
              分型、笔、线段、中枢、买卖点五个图层可以逐个开关，只看你关心的那一层。
            </p>
            <p className="mt-3">
              图例里的术语和买卖点标签都可以直接点开对应的学习词条，不用在两个页面之间来回找。
            </p>
          </Section>

          <Section title="怎么删除账号？删了还能恢复吗？">
            <p>
              在 App 内<strong>「我的 → 删除账号」</strong>即可自助删除，会有二次确认。
            </p>
            <p className="mt-3">
              删除会<strong>永久移除</strong>你的账号及关联数据，
              <strong>不可恢复</strong>。请务必确认后再操作。
              如果你已经无法登录，也可以发邮件请我们代为删除。
            </p>
            <p className="mt-3">
              注意：删除账号不会自动取消 App Store 订阅，订阅需要单独在
              「iPhone 设置 → Apple 账户 → 订阅」里取消。
            </p>
          </Section>

          <Section title="系统要求">
            <p>
              需要 <strong>iOS 17.0 或更高版本</strong>的 iPhone。当前版本暂未适配 iPad。
              支持简体中文与英文，跟随系统语言，也可以在「我的 → 语言」里手动切换。
            </p>
          </Section>
        </div>

        <p className="mt-12 border-t border-border pt-6 text-sm text-muted-foreground">
          另见{' '}
          <Link href="/privacy" className="text-primary underline underline-offset-4">
            隐私政策
          </Link>
          {' '}和{' '}
          <Link href="/terms" className="text-primary underline underline-offset-4">
            服务条款
          </Link>
          。
        </p>
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
