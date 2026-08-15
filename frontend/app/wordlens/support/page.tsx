import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: '支持与帮助 · 鹦鹉背单词',
  description: '鹦鹉背单词（WordLens）iOS 应用的使用帮助、常见问题与联系方式',
}

const UPDATED = '2026 年 8 月 15 日'
const CONTACT = 'zfleo.sg@gmail.com'

export default function WordLensSupportPage() {
  return (
    <main className="bg-background text-foreground min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回首页
        </Link>

        <h1 className="mt-6 text-3xl font-bold tracking-tight">支持与帮助</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          「鹦鹉背单词」iOS 应用 · 最后更新：{UPDATED}
        </p>

        {/* 联系方式放最上面：来支持页的人多半是遇到问题了，别让他先读一堆 FAQ */}
        <div className="mt-10 rounded-xl border border-border bg-muted/30 p-6">
          <h2 className="text-lg font-semibold">直接联系我们</h2>
          <p className="mt-2 text-[15px] leading-7 text-muted-foreground">
            遇到问题、有功能建议，或需要帮忙处理账号，发邮件即可，通常 1–2 个工作日内回复。
          </p>
          <a
            href={`mailto:${CONTACT}?subject=${encodeURIComponent('【鹦鹉背单词】问题反馈')}`}
            className="mt-4 inline-block text-lg font-medium text-primary underline underline-offset-4"
          >
            {CONTACT}
          </a>
          <p className="mt-4 text-sm text-muted-foreground">
            为了更快定位问题，邮件里麻烦附上：你的注册邮箱、iPhone 型号与 iOS 版本、
            App 版本号（在「设置 → 关于 → 版本」可以看到），以及问题的截图。
          </p>
        </div>

        <div className="mt-12 space-y-8 text-[15px] leading-7">
          <Section title="注册时收不到验证码？">
            <p>
              注册需要验证邮箱：填写邮箱后点「发送验证码」，我们会发一个 6 位验证码到该邮箱，
              输入后才会创建账号。这样能避免因为邮箱填错，导致以后无法找回密码。
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>先<strong>检查垃圾邮件文件夹</strong>，这是最常见的原因</li>
              <li>确认邮箱地址没有拼错（多打一个字母、`.com` 写成 `.con` 都很常见）</li>
              <li>验证码 <strong>10 分钟</strong>内有效，两次发送需间隔 60 秒</li>
              <li>提示「该邮箱已被注册」说明你之前注册过，请直接登录或使用「忘记密码」</li>
            </ul>
          </Section>

          <Section title="忘记密码了怎么办？">
            <p>
              在登录页点<strong>「忘记密码？」</strong>，填写注册时使用的邮箱，
              我们会给这个邮箱发一个 6 位验证码。在 App 里输入验证码，就能直接设置新密码。
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>验证码 <strong>10 分钟</strong>内有效</li>
              <li>两次发送之间需间隔 60 秒</li>
              <li>连续输错 5 次，验证码会立即失效，需要重新获取</li>
              <li>没收到邮件请先<strong>检查垃圾邮件文件夹</strong></li>
            </ul>
            <p className="mt-3">
              如果邮箱已经无法接收邮件（比如注册时填错了），请通过上方邮箱联系我们协助处理。
            </p>
          </Section>

          <Section title="拍照识别很慢，是卡住了吗？">
            <p>
              没有卡住。识别需要把图片交给 AI 模型处理，通常需要 <strong>15～50 秒</strong>，
              图片里单词越多耗时越长。识别过程中会显示扫描动画和已识别的单词数量，
              只要动画还在转就是正常的。
            </p>
            <p className="mt-3">
              如果超过一分钟仍未完成，多半是网络不稳定，可以退出重试。
            </p>
          </Section>

          <Section title="识别结果不准，漏词或者认错了怎么办？">
            <p>
              识别由 AI 模型完成，会受图片清晰度、光线、字体和排版影响。提高准确率的几个办法：
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>让书页尽量摊平，避免弯曲和阴影</li>
              <li>正对着拍，减少倾斜和透视变形</li>
              <li>一次拍一页或半页，不要一张照片塞太多内容</li>
              <li>手写体、艺术字、极小字号的识别率会明显下降</li>
            </ul>
            <p className="mt-3">
              识别结果在加入生词库之前可以逐个取消勾选，不需要的词不会被添加。
            </p>
          </Section>

          <Section title="点「拍照」没反应，或者屏幕是黑的">
            <p>
              这是相机权限被拒绝导致的。请到 iPhone 的
              <strong>「设置 → 鹦鹉背单词 → 相机」</strong>打开权限；
              App 内也会弹出提示并提供「去设置」的快捷入口。
            </p>
            <p className="mt-3">
              不想开相机权限也没关系——<strong>「从相册选择」不需要任何权限</strong>，
              先用系统相机拍好、再从相册导入，功能完全一样。
            </p>
          </Section>

          <Section title="语音听写用不了，或者总是判错">
            <p>
              语音听写需要<strong>麦克风</strong>和<strong>语音识别</strong>两项权限，
              缺一不可。App 会提示具体缺哪一项，并提供「去设置」入口。
            </p>
            <p className="mt-3">
              语音识别由 iOS 系统完成，需要联网，且会受口音和环境噪音影响。
              听写时建议<strong>逐个字母念</strong>（例如「A-P-P-L-E」），比整词朗读准确得多。
            </p>
            <p className="mt-3">
              识别不准也不影响使用——听写<strong>本来就可以直接打字</strong>，
              语音只是可选的输入方式。
            </p>
          </Section>

          <Section title="锁屏后朗读就停了">
            <p>请依次检查：</p>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              <li>
                在「设置 → 发音设置」中打开<strong>「自动发音」</strong>。
                出于对使用场景的考虑（可能在教室、会议、地铁里），这个开关<strong>默认是关闭的</strong>。
              </li>
              <li>在学习页点击中间的播放按钮，确认前台已经在朗读</li>
              <li>确认手机没有开启静音，且音量不为零</li>
            </ul>
            <p className="mt-3">
              以上都正常时，锁屏和切到后台都会继续朗读，锁屏界面会显示当前单词。
            </p>
          </Section>

          <Section title="复习安排是怎么算的？">
            <p>
              基于<strong>间隔重复算法（SM-2）</strong>。每次复习你给出的评分（不认识 / 模糊 / 认识）
              会调整这个词的下次出现时间：记得越牢，间隔拉得越长；记不住的词会更频繁地回来。
            </p>
            <p className="mt-3">
              单词会按状态自动归入「不认识 / 模糊 / 认识」三组，在生词库页可以分别查看。
              每个词的具体复习间隔和下次复习时间，在单词详情页可以看到。
            </p>
          </Section>

          <Section title="怎么删除账号？删了还能恢复吗？">
            <p>
              在 App 内<strong>「设置 → 删除账号」</strong>即可自助删除，需要输入密码二次确认。
            </p>
            <p className="mt-3">
              删除会<strong>立即永久清除</strong>你的账号、全部生词、复习进度和自建歌单，
              <strong>不设回收站、不可恢复</strong>。请务必确认后再操作。
            </p>
            <p className="mt-3">
              如果你已无法登录（例如忘记密码），也可以发邮件请我们代为删除。
            </p>
          </Section>

          <Section title="换手机后数据还在吗？">
            <p>
              在。生词库、复习进度和歌单都存在服务器上，与你的账号绑定。
              在新设备上用同一个邮箱登录即可看到全部数据。
            </p>
            <p className="mt-3">
              发音口音、语速、自动发音开关这类偏好设置保存在设备本地，换设备后需要重新设置。
            </p>
          </Section>

          <Section title="收费吗？">
            <p>
              当前完全免费，没有广告，也没有内购。若未来推出付费功能，
              我们会提前在 App 内明确告知，不会影响你已有数据的访问。
            </p>
          </Section>

          <Section title="系统要求">
            <p>需要 <strong>iOS 17.6 或更高版本</strong>的 iPhone。当前版本暂未适配 iPad。</p>
          </Section>
        </div>

        <p className="mt-12 border-t border-border pt-6 text-sm text-muted-foreground">
          另见{' '}
          <Link href="/wordlens/privacy" className="text-primary underline underline-offset-4">
            隐私政策
          </Link>
          {' '}和{' '}
          <Link href="/wordlens/terms" className="text-primary underline underline-offset-4">
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
