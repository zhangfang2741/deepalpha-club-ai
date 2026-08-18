# App Review 回复（Guideline 2.1 - Information Needed）

Apple 要求补充 7 项材料。

- **第 1 项**（屏幕录像）需要你在真机上录制，脚本见文末。
- **第 2~7 项**已写成可直接粘贴的完整文本，中英两版内容一致，选一版用即可。
  在「解决方案中心」回复时贴上，同时建议一并填进「App 审核信息 → 备注」，
  供后续版本复用。

✅ 设备与系统版本已填好（iPhone 16 Pro / iOS 26.6），文本可直接整段复制使用。

---

## 1. 屏幕录像（需你在真机上录制）

见本文件末尾的「录屏脚本」。

---

## 回复文本 · 中文版（含全部 2~7 项）

> ⚠️ App Review 的审核员是国际团队，**用英文回复通常更稳妥**，避免因语言问题多来回一轮。
> 下方英文版内容与本中文版完全一致，可直接使用。若你确定只面向中国区、或倾向中文，
> 用这一版即可。

```
感谢审核。以下是你们要求补充的信息。

────────────────────────────────────────
2. 测试过的设备与系统版本
────────────────────────────────────────
- iPhone 16 Pro，iOS 26.6（真机）

录像即在该设备上录制。提交前已在这台真机上完整验证过：注册、登录、拍照识别、
复习、听写、后台朗读、删除账号——录像中均有呈现。

App 的 deployment target 为 iOS 17.6。

────────────────────────────────────────
3. App 功能与目标用户
────────────────────────────────────────
「鹦鹉背单词」是一款面向中文用户的英语单词学习工具。

解决的问题：
阅读英文教材、试卷、外刊时遇到生词，需要逐个查词典再手动抄进笔记本，
过程缓慢且打断阅读。

工作方式：
用户拍下含英语单词的书页，App 一次识别出图中所有生词，自动配上国际音标、
词性、中文释义、词源和例句，存入个人生词库，并按 SM-2 间隔重复算法安排复习。

目标用户：
- 备考四六级、考研、雅思、托福的学生
- 阅读英文原版书、外刊、论文的读者
- 想利用通勤时间听着复习单词的上班族

App 完全免费，无广告，无内购，无订阅。

────────────────────────────────────────
4. 设置与访问说明
────────────────────────────────────────
测试账号（请使用「邮箱」方式登录）：
  邮箱：appreview@deepalpha.club
  密码：AppReview2026

重要 —— 如何登录：
登录页顶部有「手机号 / 邮箱」两个切换项。手机号验证码由中国大陆的短信服务
发送，非中国大陆号码无法接收。请点击「邮箱」，用上面的测试账号登录。

该账号已预置 18 个生词、2 个自建歌单，以及三种复习状态的单词，登录后无需
录入任何数据即可体验全部功能。

主要功能及入口：

a) 拍照识词 —— 标签一「首页」
   点「拍照」调用相机，或点「从相册选择」导入已有图片。任何含英语单词的
   页面都可以。
   注意：识别需调用视觉模型，通常耗时 15~50 秒，期间会显示扫描动画和已识别
   的单词数量。
   注意：若拒绝相机权限，「从相册选择」仍可正常使用，且不需要任何权限。

b) 复习 —— 标签二「学习」
   点击卡片翻转查看释义，左右滑动评分。评分会调整该词的下次复习间隔
   （SM-2 算法）。

c) 听写 —— 标签二「学习」，右上角切换到「听写」
   可以打字，也可以点麦克风逐个字母念出（例如 A-P-P-L-E）。
   打字不需要任何权限，麦克风是可选的。

d) 生词库 —— 标签三「生词库」
   按状态筛选（不认识 / 模糊 / 认识）、搜索、管理歌单。

e) 设置 —— 标签四「设置」
   发音偏好、隐私政策、服务条款、删除账号。

关于后台音频权限（UIBackgroundModes: audio）—— 如何验证：
「通勤时听着背单词」是本 App 的核心使用场景之一。
  1. 进入「设置 → 发音设置」，打开「自动发音」
     （该开关默认关闭，因为用户可能正在教室、会议或公共交通上。）
  2. 回到「学习」标签，点击中间的播放按钮
  3. App 会连续朗读单词及其例句
  4. 此时锁屏或切到其他 App，朗读会继续，锁屏界面显示当前单词
后台音频仅用于此朗读场景，不做任何其他后台活动。

关于删除账号：
「设置 → 删除账号」，需重新输入密码。删除立即生效且不可恢复——账号、全部
生词、复习记录和歌单会被彻底清除，不设回收站或宽限期。
（请勿在测试账号上执行；若已删除，可用同一邮箱重新注册。）

────────────────────────────────────────
5. 使用的外部服务
────────────────────────────────────────
- Google Gemini（视觉模型）
  识别用户照片中的英语单词，并生成音标、释义、词源和例句。图片仅为完成本次
  实时请求而传输，从不写入我们的数据库或磁盘，请求结束即从内存释放。传输时
  不附带任何用户身份信息。

- Apple SFSpeechRecognizer（系统框架）
  将用户念出的字母转为文字，用于听写判定。音频完全由 iOS 处理，不经过我们的
  服务器。

- MiniMax（语音合成）
  生成单词和例句的发音音频。仅发送文本，不含任何用户身份信息。

- 阿里云邮件推送
  发送邮箱注册和找回密码的 6 位验证码。

- 阿里云号码认证服务（短信）
  发送并核验手机号注册和找回密码的 6 位验证码。验证码由阿里云生成和核验，
  我们不接触其明文。

- Railway（应用托管与数据库）
- Cloudflare（域名解析）

本 App 不含任何广告 SDK、不含任何分析统计 SDK，不做跨应用或跨网站追踪，
因此未请求 App 追踪透明度（ATT）授权。

────────────────────────────────────────
6. 地区差异
────────────────────────────────────────
App 的功能与内容在所有地区完全一致，仅注册方式有一处差异：

- 邮箱注册与登录：全球可用。
- 手机号注册与登录：短信验证码通过中国大陆的短信服务发送，非中国大陆号码
  无法接收，此类用户请使用邮箱注册。

两种方式创建的账号类型与功能完全相同，登录页可随时切换。

所有学习功能（拍照识别、复习、听写、歌单、发音）在全球范围内表现一致。

────────────────────────────────────────
7. 受监管行业 / 受保护的第三方材料
────────────────────────────────────────
本 App 不属于受监管行业，也不包含任何受保护的第三方材料。

所有单词释义、国际音标、词源和例句均由 Google Gemini 模型在识别时实时生成，
不复制自任何词典或其他受版权保护的来源。

所有发音音频（单词与例句）均由 MiniMax 语音合成服务生成——这是我们付费订阅
的商业服务——并通过我们自己的后端请求。

本 App 不捆绑、不展示、也不访问任何授权词典内容、录音或其他第三方受保护作品。
```

---

## 回复文本 · 英文版（含全部 1~7 项，推荐使用）

> 直接整段复制到解决方案中心，视频作为附件一起上传（`wordlens-review-demo.mp4`，7.7 MB）。
> 时间戳已按实际录像逐帧核对过，审核员可据此直接跳转。

```
Thank you for reviewing our app. Please find all requested information below.

────────────────────────────────────────
1. SCREEN RECORDING
────────────────────────────────────────
The screen recording is attached to this message (wordlens-review-demo.mp4).
Captured on a physical iPhone 16 Pro running iOS 26.6 (the current release).
Duration 4:31. The recording begins with launching the app from the Home Screen.

Timestamps for the flows you asked about:

  0:00  App launched from the Home Screen
  0:04  Account registration begins (phone number method)
  0:32  SMS verification code received on-device and entered
  0:36  Registration complete, signed in
  0:40  Sign out (with confirmation dialog)
  0:48  Sign in with the demo account (email method)
  1:20  ** Camera permission prompt **
  1:28  Photo of a printed page captured; recognition in progress (~20 s)
  1:44  Recognition results; words added to the vocabulary list
  1:56  Vocabulary list: status filters, search, and two custom playlists
  2:00  Review: card flip to reveal the definition, swipe to rate recall
  2:28  Dictation mode
  2:30  ** Speech recognition permission prompt **
  2:31  ** Microphone permission prompt **
  2:33  Spelling a word aloud letter by letter; result graded
  3:08  Background audio: screen locked, playback continues, Lock Screen shows
        the current word
  3:44  Signed back in with the phone account created at 0:04
  4:04  Account deletion: warning list, password confirmation, permanent delete
  4:24  Returned to the sign-in screen; the account no longer exists

All three permission prompts (camera, microphone, speech recognition) are shown
being requested and granted. The app has no paid content, no subscriptions, and
no user-generated content shared between users, so those flows do not apply.

────────────────────────────────────────
2. DEVICES AND OS VERSIONS TESTED
────────────────────────────────────────
- iPhone 16 Pro, iOS 26.6  (physical device)

The screen recording above was captured on this device. All core flows —
registration, sign-in, photo recognition, review, dictation, background playback,
and account deletion — were verified on it before submission, as shown in the
recording.

The app's deployment target is iOS 17.6.

────────────────────────────────────────
3. APP FUNCTION AND TARGET AUDIENCE
────────────────────────────────────────
"鹦鹉背单词" (Parrot Vocabulary) is an English vocabulary learning tool for
Chinese-speaking learners.

The problem it solves:
When reading English textbooks, exam papers, or magazines, a learner encounters
unfamiliar words and must look each one up in a dictionary and copy it into a
notebook by hand. This is slow and repeatedly interrupts reading.

How it works:
The user photographs a page containing English words. The app recognizes all of
the words in the image at once and automatically attaches the IPA transcription,
part of speech, Chinese definition, etymology, and an example sentence. Words are
saved to a personal vocabulary list and scheduled for review using the SM-2
spaced repetition algorithm. Words can also be reviewed by listening, including
while the screen is locked.

Target audience:
- Students preparing for CET-4/6, postgraduate entrance exams, IELTS, or TOEFL
- Readers of English books, magazines, and academic papers
- Commuters who want to review vocabulary by listening

The app is free. It has no advertising, no in-app purchases, and no subscriptions.

────────────────────────────────────────
4. SETUP AND ACCESS INSTRUCTIONS
────────────────────────────────────────
DEMO ACCOUNT — please sign in with the EMAIL method:

  Email:    appreview@deepalpha.club
  Password: AppReview2026

IMPORTANT: The sign-in screen has a segmented control at the top offering
"手机号" (phone) and "邮箱" (email). Phone verification codes are delivered by a
mainland-China SMS provider and cannot be received by non-Chinese phone numbers.
Please tap "邮箱" (email) and use the credentials above. This is demonstrated in
the recording at 0:48.

The demo account is pre-populated with vocabulary words in all three review
states and two custom playlists, so every feature can be exercised immediately
without adding any data.

MAIN FEATURES AND WHERE TO FIND THEM:

a) Photo recognition — tab 1 "首页"
   "拍照" opens the camera; "从相册选择" imports an existing image. Any page
   containing English words works.
   Recognition calls a vision model and typically takes 15-50 seconds. A scanning
   animation with a running word count is displayed while it works.
   If camera permission is denied, "从相册选择" still works and requires no
   permissions at all.

b) Review — tab 2 "学习"
   Tap the card to flip it and reveal the definition; swipe to rate recall. The
   rating adjusts the next review interval (SM-2).

c) Dictation — tab 2 "学习", switch to "听写" at the top right
   Type the word, or tap the microphone and spell it out letter by letter
   (e.g. "A-P-P-L-E"). Typing requires no permissions; the microphone is optional.

d) Vocabulary list — tab 3 "生词库"
   Filter by status, search, and manage playlists.

e) Settings — tab 4 "设置"
   Pronunciation preferences, privacy policy, terms of service, account deletion.

BACKGROUND AUDIO (UIBackgroundModes: audio) — HOW TO VERIFY:
Reviewing vocabulary by listening while commuting is a core use case.
  1. 设置 → 发音设置, turn ON "自动发音".
     This is OFF by default, because the user may be in a classroom, a meeting,
     or on public transport and should not be surprised by sound.
  2. Return to tab "学习" and tap the play button in the center.
  3. The app reads each word and its example sentence continuously.
  4. Lock the screen or switch to another app — playback continues and the Lock
     Screen shows the current word.
This is shown in the recording at 3:08. Background audio is used solely for this
playback; the app performs no other background activity.

ACCOUNT DELETION:
设置 → 删除账号, then re-enter the password. Deletion is immediate and permanent:
the account, all vocabulary, review history, and playlists are erased, with no
recovery period. Shown in the recording at 4:04.
(Please avoid running this on the demo account. If it is deleted, the same email
can simply be registered again.)

────────────────────────────────────────
5. EXTERNAL SERVICES USED
────────────────────────────────────────
- Google Gemini (vision and language model)
  Recognizes English words in the user's photo and generates the IPA
  transcription, definition, etymology, and example sentence. The image is
  transmitted for real-time processing only; it is never written to our database
  or to disk, and is released from memory as soon as the request completes. No
  user identity is sent with the image.

- Apple SFSpeechRecognizer (system framework)
  Converts the letters the user speaks into text for dictation grading. Audio is
  handled entirely by iOS and never reaches our servers.

- MiniMax (text-to-speech)
  Synthesizes the pronunciation audio for both words and example sentences. Only
  the text is sent; no user identity is included. Requests are proxied through
  our own backend so that the provider key is never shipped in the app.

- Alibaba Cloud DirectMail (transactional email)
  Delivers the 6-digit verification code for email registration and password
  reset.

- Alibaba Cloud Number Verification Service (SMS)
  Delivers and validates the 6-digit code for phone registration and password
  reset. The code is generated and verified by Alibaba Cloud; we never handle it
  in plaintext.
  Note: China's carrier regulations do not permit custom SMS sender signatures
  for our account tier, so the verification SMS is sent under the provider's
  generic signature 【恒创联众】 rather than the app name. This is visible in the
  recording at 0:32. The app's registration screen tells the user which signature
  to expect so the message is not mistaken for spam.

- Railway (application hosting and database)
- Cloudflare (DNS)

The app contains NO advertising SDKs and NO analytics SDKs, and performs no
cross-app or cross-website tracking. It therefore does not request App Tracking
Transparency authorization.

────────────────────────────────────────
6. REGIONAL DIFFERENCES
────────────────────────────────────────
The app's features and content are identical in every region, with one exception
that concerns account creation only:

- EMAIL registration and sign-in: available worldwide.
- PHONE NUMBER registration and sign-in: the SMS verification code is delivered
  through a mainland-China SMS provider. Users with non-Chinese phone numbers
  will not receive it and should register with an email address instead.

Both methods create the same kind of account with identical functionality, and
the sign-in screen lets the user switch between them at any time.

All learning features — photo recognition, review, dictation, playlists, and
pronunciation — behave identically in all regions.

────────────────────────────────────────
7. REGULATED INDUSTRY / PROTECTED THIRD-PARTY MATERIAL
────────────────────────────────────────
The app does not operate in a regulated industry and does not include, display,
or access any protected third-party material.

- Definitions, IPA transcriptions, etymologies, and example sentences are
  generated by Google's Gemini model at the moment of recognition. They are not
  copied from any dictionary or other copyrighted source.
- All pronunciation audio, for both words and example sentences, is synthesized
  by MiniMax text-to-speech, a commercial service we subscribe to, and is
  requested through our own backend.
- The images the user photographs are their own material and are not retained.

The app bundles no licensed dictionary content, no audio recordings, and no other
third-party protected works.

Thank you for your time. Please let us know if anything else would be helpful.
```

---

## 附：原决策记录（已执行方案 A）

Apple 第 7 条问的是「受监管行业或包含受保护的第三方材料，请提供授权文件」。

**本 App 目前从 `https://dict.youdao.com/dictvoice` 拉取单词发音**
（见 `ios/WordLens/Views/Components/PronounceButton.swift:520`，客户端直连）。

有道词典的发音录音属于第三方受版权保护的材料，而该接口是非公开接口，
网易有道未对第三方应用发布过公开许可。

### 两条路

**A. 换掉有道（推荐）**

把单词发音改用 MiniMax TTS——后端已经在给例句用同一套服务，改动很小。
之后第 5 项的外部服务清单里不再出现有道，第 7 项可以直接回答
「不包含受保护的第三方材料」。

代价：需要重新打包（构建号改为 `1.0 (2)`）、重新上传、重新排队 24~48 小时。

**B. 保留有道，如实申报**

第 5 项列出有道，第 7 项说明该接口公开可访问。
风险：Apple 很可能追问授权文件；提供不了则可能要求移除该功能，
届时仍要走 A 的流程，且多绕一圈、多等一轮。

另外与版权无关的风险：该接口无文档、无 SLA，有道随时可加校验或封禁，
届时线上所有用户的单词发音同时失效，而 App Store 上的二进制改不了。

---

## 录屏脚本（第 1 项）

**设备**：iPhone 16 Pro / iOS 26.6（CQL-IPHONE）。App 已卸载重装，权限均未授权。

### 录制方式：用 iPhone 自带录屏（推荐）

**不要用 QuickTime 录连接的真机**：iPhone 一锁屏，屏幕镜像就断开，录制随之中止，
而第 16 步演示后台音频恰恰需要锁屏。自带录屏锁屏后会继续录，唤醒时能拍到锁屏
界面上的媒体卡片，这是后台音频最直接的证据。

1. 设置 → 控制中心 → 添加「**屏幕录制**」
2. 右上角下拉呼出控制中心，点录制按钮，等 3 秒倒计时
3. **不用开麦克风** —— 自带录屏默认就录 App 内的声音；开了麦反而会混进环境噪音
4. 按下面的步骤操作 → 再次点控制中心的录制按钮停止
5. 录像存在「照片」App。导到 Mac：数据线连接后用「图像捕捉」或「照片」App 导出，
   也可以 AirDrop

> 如果因故必须用 QuickTime（连 Mac，文件 → 新建影片录制，摄像头和麦克风都选
> CQL-IPHONE），那么第 16 步不要真的锁屏，改成：上滑回主屏幕 → 下拉呼出控制中心
> → 展示「正在播放」卡片上的当前单词。这同样能证明 App 退到后台后朗读仍在继续。

### 步骤（建议 3~5 分钟）

> **注册用手机号，不用邮箱**：短信直接发到这台手机，验证码全程在画面里；
> 邮箱验证码在电脑上收，录屏拍不到，审核员会看到「输入验证码」这步凭空跳过。

| # | 动作 | 要点 |
|---|------|------|
| 1 | 从桌面点开「鹦鹉背单词」 | Apple 要求录像从启动 App 开始 |
| 2 | 停在登录页约 2 秒 | 展示顶部「手机号 / 邮箱」切换 |
| 3 | 点「还没有账号？去注册」 | |
| 4 | 保持「手机号」，输入本机号码，点「发送验证码」 | |
| 5 | **等短信到达，从通知或短信 App 读出验证码** | 全程在画面内，这是关键 |
| 6 | 填验证码和密码，完成注册 | ✅ **注册流程已展示** |
| 7 | 进入 App 后，去「设置 → 退出登录」 | 展示二次确认弹窗 |
| 8 | 切到「邮箱」，用 `appreview@deepalpha.club` / `AppReview2026` 登录 | ✅ **登录流程已展示**，且账号内有预置数据 |
| 9 | 首页点「拍照」 | ⚠️ **相机权限弹窗必须入镜**，点「允许」 |
| 10 | 拍一页英文（书、杂志、电脑屏幕上的英文网页都行） | 识别要 15~50 秒，**别剪掉**，让审核员看到进度反馈 |
| 11 | 勾选几个词，加入生词库 | |
| 12 | 切「学习」标签，点卡片翻转，滑动评分 **2~3 个就停** | 别把 18 个词全复习完，否则队列清空不好演示 |
| 13 | 右上角切「听写」，点麦克风 | ⚠️ **麦克风 + 语音识别两个权限弹窗必须入镜** |
| 14 | 逐字母念出一个单词（如 A-P-P-L-E），展示判定结果 | |
| 15 | 「设置 → 发音设置」打开「自动发音」，回学习页点播放 | |
| 16 | **按侧边键锁屏**，停 2 秒，再**唤醒** | 黑屏期间朗读不停；唤醒后锁屏卡片显示当前单词，停留 3~5 秒 |
| 17 | 解锁，切「生词库」标签 | 展示状态筛选、搜索、两个歌单 |
| 18 | 「设置 → 退出登录」，改用第 6 步注册的**手机号账号**登录 | |
| 19 | 「设置 → 删除账号」，输密码，确认删除 | ✅ **删除账号流程已展示** |
| 20 | 回到登录页，录制结束 | |

### 三条硬要求（漏了就白录）

1. **注册、登录、删除账号**三个完整流程 —— Apple 逐项点名要求
2. **相机、麦克风、语音识别**三个权限弹窗 —— 原话是 "Any prompts requesting
   access to sensitive data or device capabilities"
3. **真机 + 最新系统** —— 已满足（iPhone 16 Pro / iOS 26.6）

⚠️ 第 19 步删的是**你自己注册的手机号账号**，不是 `appreview@deepalpha.club`。
那个账号审核员还要用，别删。

### 录完

上传到可公开访问的地方（YouTube 不公开链接、Google Drive 共享链接等），
把链接贴进解决方案中心的回复；也可以直接在解决方案中心上传文件。
