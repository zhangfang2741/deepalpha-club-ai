# App Review 回复（Guideline 2.1 - Information Needed）

Apple 要求补充 7 项材料。

- **第 1 项**（屏幕录像）需要你在真机上录制，脚本见文末。
- **第 2~7 项**已写成可直接粘贴的完整文本，中英两版内容一致，选一版用即可。
  在「解决方案中心」回复时贴上，同时建议一并填进「App 审核信息 → 备注」，
  供后续版本复用。

⚠️ 只有两处需要你填：中英文版本里的机型和系统版本
（`iPhone <你的机型>, iOS <你的系统版本>`）。

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
- iPhone <你的机型>，iOS <你的系统版本>（真机）
- iPhone 11 Pro Max 模拟器，iOS 26.5（仅用于界面核对）

提交前已在真机上完整验证过：注册、登录、拍照识别、复习、听写、删除账号。

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

## 回复文本 · 英文版（含全部 2~7 项，推荐使用）

```
Thank you for reviewing our app. Please find the requested information below.

────────────────────────────────────────
2. DEVICES AND OS VERSIONS TESTED
────────────────────────────────────────
- iPhone <你的机型>, iOS <你的系统版本>  (physical device)
- iPhone 11 Pro Max simulator, iOS 26.5  (UI verification only)

All core flows (registration, login, photo recognition, review, dictation,
account deletion) were verified on the physical device before submission.

────────────────────────────────────────
3. APP FUNCTION AND TARGET AUDIENCE
────────────────────────────────────────
"鹦鹉背单词" (Parrot Vocabulary) is an English vocabulary learning tool for
Chinese-speaking learners.

Problem it solves:
When reading English textbooks, exam papers, or magazines, learners find
unfamiliar words and must look each one up in a dictionary, then manually copy
it into a notebook. This is slow and interrupts reading.

How it works:
The user photographs a page containing English words. The app recognizes all
unfamiliar words in the image at once and automatically attaches the IPA
pronunciation, part of speech, Chinese definition, etymology, and an example
sentence. Words are saved to a personal vocabulary list and scheduled for
review using the SM-2 spaced repetition algorithm.

Target audience:
- Students preparing for CET-4/6, postgraduate entrance exams, IELTS, TOEFL
- Readers of English books, magazines, and academic papers
- Commuters who want to review vocabulary by listening

The app is free, contains no advertising, and has no in-app purchases or
subscriptions.

────────────────────────────────────────
4. SETUP AND ACCESS INSTRUCTIONS
────────────────────────────────────────
DEMO ACCOUNT (please use the EMAIL login method):
  Email:    appreview@deepalpha.club
  Password: AppReview2026

IMPORTANT — HOW TO LOG IN:
The login screen offers two methods via a toggle at the top: "手机号" (phone)
and "邮箱" (email). Phone verification codes are delivered by a mainland-China
SMS provider and CANNOT be received by non-Chinese phone numbers. Please tap
"邮箱" (email) and sign in with the demo account above.

The demo account is pre-populated with 18 vocabulary words, 2 custom playlists,
and words in all three review states, so every feature can be exercised
immediately without adding data.

MAIN FEATURES AND HOW TO ACCESS THEM:

a) Photo recognition — Tab 1 "首页"
   Tap "拍照" to use the camera, or "从相册选择" to import an existing image.
   Any page containing English words works.
   NOTE: Recognition calls a vision model and typically takes 15-50 seconds.
   A scanning animation with a running word count is shown while it works.
   NOTE: If camera permission is denied, "从相册选择" still works and requires
   no permissions at all.

b) Review — Tab 2 "学习"
   Tap the card to flip it and reveal the definition. Swipe left/right to rate
   your recall. The rating adjusts the next review interval (SM-2 algorithm).

c) Dictation — Tab 2 "学习", toggle "听写" at the top right
   Type the word, or tap the microphone and spell it out letter by letter
   (e.g. "A-P-P-L-E"). Typing works without any permission; the microphone is
   optional.

d) Vocabulary list — Tab 3 "生词库"
   Filter by status (不认识 / 模糊 / 认识), search, and manage playlists.

e) Settings — Tab 4 "设置"
   Pronunciation preferences, privacy policy, terms of service, account
   deletion.

BACKGROUND AUDIO (UIBackgroundModes: audio) — HOW TO VERIFY:
Listening to vocabulary while commuting is a core use case of this app.
  1. Go to 设置 → 发音设置 and turn ON "自动发音".
     (This is OFF by default out of respect for users who may be in a
     classroom, meeting, or on public transport.)
  2. Return to tab "学习" and tap the play button in the center.
  3. The app reads each word and its example sentence continuously.
  4. Lock the screen or switch to another app — playback continues and the
     Lock Screen shows the current word.
Background audio is used solely for this playback; the app performs no other
background activity.

ACCOUNT DELETION:
设置 → 删除账号. Requires re-entering the password. Deletion is immediate and
permanent — the account, all vocabulary, review history, and playlists are
erased with no recovery period.
(Please avoid running this on the demo account; if it is deleted, the same
email can be registered again.)

────────────────────────────────────────
5. EXTERNAL SERVICES USED
────────────────────────────────────────
- Google Gemini (vision model)
  Recognizes English words in the user's photo and generates the IPA,
  definition, etymology, and example sentence. The image is transmitted for
  real-time processing only; it is never written to our database or disk and
  is released from memory as soon as the request completes. No user identity
  is sent with the image.

- Apple SFSpeechRecognizer (system framework)
  Converts the user's spoken letters to text for dictation grading. Audio is
  handled entirely by iOS and never reaches our servers.

- MiniMax (text-to-speech)
  Generates audio for example sentences. Only the sentence text is sent; no
  user identity is included.

- Alibaba Cloud DirectMail (email delivery)
  Sends the 6-digit verification code for email registration and password
  reset.

- Alibaba Cloud Number Verification Service (SMS)
  Sends and verifies the 6-digit code for phone registration and password
  reset. The code is generated and validated by Alibaba Cloud; we never see it
  in plaintext.

- Railway (application hosting and database)
- Cloudflare (DNS)

The app contains NO advertising SDKs, NO analytics SDKs, and performs no
cross-app or cross-website tracking. It therefore does not request App
Tracking Transparency authorization.

────────────────────────────────────────
6. REGIONAL DIFFERENCES
────────────────────────────────────────
The app's features and content are identical in all regions, with one
exception related to account registration:

- EMAIL registration and login: available worldwide.
- PHONE NUMBER registration and login: the SMS verification code is delivered
  through a mainland-China SMS provider. Users with non-Chinese phone numbers
  will not receive the code and should use email registration instead.

Both methods create the same type of account with identical functionality.
The login screen lets the user switch between them at any time.

All learning features (photo recognition, review, dictation, playlists,
pronunciation) work identically worldwide.

────────────────────────────────────────
7. REGULATED INDUSTRY / PROTECTED THIRD-PARTY MATERIAL
────────────────────────────────────────
The app does not operate in a regulated industry and does not include any
protected third-party material.

All word definitions, IPA transcriptions, etymologies, and example sentences
are generated by Google's Gemini model at the time of recognition; they are not
copied from any dictionary or other copyrighted source.

All pronunciation audio (both words and example sentences) is synthesized by
MiniMax text-to-speech, a commercial service we subscribe to, and is requested
through our own backend.

The app does not bundle, display, or access any licensed dictionary content,
audio recordings, or other third-party protected works.
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

要求：**真机**（不能用模拟器）、**最新系统**、**从启动 App 开始**。

iPhone 录屏：设置 → 控制中心 → 添加「屏幕录制」，然后从右上角下拉呼出控制中心点击录制。

建议时长 3~5 分钟，按顺序走：

| # | 动作 | 要点 |
|---|------|------|
| 1 | **删除已装的 App，重新安装并启动** | Apple 要求「begin with launching the app」 |
| 2 | 停在登录页 2 秒 | 展示手机号/邮箱切换 |
| 3 | 点「去注册」，用邮箱注册一个新账号 | **必须展示注册流程**，含收验证码、输入、完成 |
| 4 | 退出登录（展示二次确认弹窗） | |
| 5 | 用 `appreview@deepalpha.club` 登录 | **展示登录流程** |
| 6 | 首页点「拍照」 | **相机权限弹窗必须入镜** |
| 7 | 拍一页英文（书、屏幕、任何印刷体都行） | 识别要等 15~50 秒，别剪掉，让 Apple 看到进度反馈 |
| 8 | 勾选若干词，加入生词库 | |
| 9 | 切「学习」标签，翻卡、评分 | |
| 10 | 切到「听写」，点麦克风 | **麦克风 + 语音识别权限弹窗必须入镜** |
| 11 | 逐字母念出一个单词，展示判定 | |
| 12 | 设置 → 发音设置 → 打开「自动发音」 | |
| 13 | 回学习页点播放，然后**锁屏** | 展示锁屏界面继续朗读、显示当前单词 |
| 14 | 解锁，切「生词库」标签 | 展示筛选、搜索、歌单 |
| 15 | 设置 → 删除账号 | **用第 3 步注册的那个账号演示**，别删 appreview |
| 16 | 完整走完删除流程（输密码 → 确认 → 回到登录页） | **必须展示删除账号流程** |

⚠️ 三类权限弹窗（相机、麦克风、语音识别）**必须出现在录像里**——
Apple 第 1 条明确要求 "Any prompts requesting access to sensitive data or
device capabilities"。所以录之前要先删掉 App 重装，否则权限已授权就不弹了。

录完上传到可公开访问的地方（YouTube 不公开链接、Google Drive 共享链接等），
把链接贴进回复。也可以直接在解决方案中心上传文件。
