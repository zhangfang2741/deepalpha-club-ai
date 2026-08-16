# App Review 回复（Guideline 2.1 - Information Needed）

Apple 要求补充 7 项材料。下面 2~6 项可直接粘贴到 App Store Connect 的
「App 审核信息 → 备注」并在解决方案中心回复；第 1 项需要你录屏；
第 7 项见文末的决策说明。

---

## 1. 屏幕录像（需你在真机上录制）

见本文件末尾的「录屏脚本」。

## 2~6 项的回复文本（英文，直接粘贴）

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

<<< 有道条目见下方第 7 项的决策说明，确定后再填 >>>

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
```

---

## 7. 受保护的第三方材料 —— 需要你先决策

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
