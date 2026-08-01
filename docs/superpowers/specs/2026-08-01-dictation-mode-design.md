# WordLens 听写模式设计

日期：2026-08-01

## 背景

WordLens 首页现在只有一种学习方式：卡片正面显示单词，点一下翻到背面看释义，再评分。
连播（`AutoplayController`）负责每个词读 3 遍、词间停顿、自动切下一词。这套流程是纯
"输入"的——用户始终在**看着答案**，无法检验自己到底能不能拼出来。

新增「听写模式」，与现有的「只听模式」二选一：单词默认藏起来，卡片本身变成填写框，
用户听音写词，写完自动判定认识/模糊/不认识并提交 SM-2。

## 已确认的决策

| 决策点 | 选择 |
|--------|------|
| 判定规则 | 归一化后完全一致=认识；小错=模糊；其余=不认识 |
| 卡片提示 | 什么都不留，卡片本身就是填写框 |
| 确定后 | 亮答案 1.5s，提交评分，自动进下一词 |
| 作用范围 | 总是生效（连播时读完 3 遍等输入；手动翻词时输入框直接就在） |
| 模式入口 | 首页顶部一个开关 |

## 一、判定模块 `Services/DictationJudge.swift`（新）

纯函数，零依赖、零状态：

```swift
enum DictationJudge {
    static func normalize(_ text: String) -> String
    static func levenshtein(_ a: [Character], _ b: [Character]) -> Int
    static func judge(input: String, answer: String) -> ReviewRating
}
```

**归一化**：转小写 → 去首尾空白 → 删除所有连字符、空格、下划线。
于是 `online-shopping` / `online shopping` / `Online Shopping` / `onlineshopping`
全折成 `onlineshopping`，连字符怎么打都算对（词库里这类复合词很多）。

**判定**：

| 条件 | 结果 |
|------|------|
| 输入为空 | 不认识 |
| 归一化后完全一致 | 认识 |
| 编辑距离在该长度允许范围内 | 模糊 |
| 其余 | 不认识 |

「允许范围」按答案长度分档（`maxFuzzyDistance(forAnswerLength:)`）：

| 答案长度 | 最多容错 |
|----------|----------|
| 1–4 | 0（错一个就是另一个词） |
| 5–7 | 1 |
| ≥8 | 2 |

**实施中修正**：初稿写的是"编辑距离 ≤ 2 且距离 < 答案长度/2"。写完测试立刻被打脸——
`cat` 写成 `cot`（3 字母、距离 1）按那条规则会判"模糊"，可这俩是彻头彻尾的两个词。
分档阈值更贴合直觉，也更好读：`card`/`cart` 判不认识，`hous`/`house` 判模糊。

## 二、模式偏好 `Models/StudyMode.swift`（新）

```swift
enum StudyMode: String, CaseIterable {
    case listenOnly   // 只听（现有行为）
    case dictation    // 听写
    static var current: StudyMode { get set }   // UserDefaults: "study_mode"
}
```

沿用仓库里既有的偏好项写法（`ReviewMode` / `PronunciationSource` 都是这个模式：
enum + 静态 current + UserDefaults 读写）。默认 `listenOnly`，保持老用户行为不变。

## 三、听写相位与连播的握手

### 相位

听写模式下每个词有两个相位，存在 `ReviewViewModel`：

```swift
enum DictationPhase: Equatable {
    case input
    case revealed(word: VocabularyWord, input: String, rating: ReviewRating)
}
```

切词时重置为 `.input` 并清空输入框。

**实施中修正**：初稿的 `.revealed` 只带 rating，界面从 `currentWord` / `dictationInput`
读实时值。这有泄题风险——提交评分会把当前词移出队列、`currentWord` 立刻指向**下一个**词，
两者之间只要有一次调度让位，亮答案的卡片就会闪出下一个词的正确拼写。改成把被判定的词和
用户输入一起快照进相位，显示内容跟队列时序彻底脱钩。

### 与连播的握手

`AutoplayController` 只加**一个**协议属性：

```swift
protocol AutoplayDataSource {
    // ...既有成员
    var autoplayCurrentWordID: String? { get }  // 判断"换词了没"用它
    var autoplayWaitsForInput: Bool { get }     // 听写模式下为 true
}
```

`runLoop` 读完 3 遍后分叉：

- **只听模式**（现状不变）：停 2 秒 → `autoplayAdvance()` → 下一词。
- **听写模式**：不停 2 秒、不主动前进，而是**轮询等到当前词发生变化**：

```swift
let original = dataSource?.autoplayCurrentWordID
while isPlaying, !Task.isCancelled, dataSource?.autoplayCurrentWordID == original {
    try? await Task.sleep(for: .milliseconds(120))
}
```

比的是 id 而不是词本身：同一个分组里可能有拼写相同的两条记录，比字符串会误判成没换。

用"当前词变了"而不是"相位变了"作为退出条件，是因为相位在 `.revealed` 的 1.5 秒里
队列**还没**前进——若按相位退出，循环会在亮答案期间把同一个词又读一遍。等词真正
换掉才继续，天然覆盖了「输入 + 亮答案 + 提交」整段。

轮询而非 continuation：`AutoplayController` 里既有的 `speakAndWait` 已经是轮询
`Pronouncer.playingWord` 的写法，保持一致；也避免 continuation 必须恰好 resume 一次
的生命周期坑。

队列播完时 `autoplayCurrentWordID` 变 nil，同样 ≠ 原值，循环退出后由既有的
空值检查收尾。

### 提交

```swift
func submitDictation() async {
    guard isDictation, dictationPhase.isInput, let word = currentWord else { return }
    let typed = dictationInput
    let rating = DictationJudge.judge(input: typed, answer: word.word)
    dictationPhase = .revealed(word: word, input: typed, rating: rating)
    Haptics.rating(rating)

    try? await Task.sleep(for: .seconds(1.5))
    // 停留期间用户可能已手动切词/停播，确认还停在同一个词才提交
    guard currentWord?.id == word.id, case .revealed = dictationPhase else { return }
    await submit(rating, keepAutoplay: true)
    resetDictation()
}
```

既有的 `submit(_:)` 结尾会 `autoplay.stop()`（评分完就该停下让用户接管），但听写模式
下评分是流程的一环、不该打断连播。所以给它加一个 `keepAutoplay: Bool = false` 参数：
默认行为完全不变（三档评分按钮仍然停连播），听写路径传 `true`。

## 四、界面

### 顶部模式开关

`topBar` 从 `[☰ 分组名] — Spacer — [进度]` 变成
`[☰ 分组名] — Spacer — [模式胶囊] — [进度]`。

模式胶囊是一个紧凑的两态按钮，点一下就切：只听显示 `🎧 只听`，听写显示 `✍️ 听写`，
听写态用主题色填充以示"当前在更严格的模式里"。

### 卡片

听写模式下不走 `flipCard`（翻卡在这里没有意义），改渲染 `dictationCard`：

- `.input` 相位：卡片中央一个大号 `TextField`，上方一行 `🔊 听音写词` 提示。
  关掉自动大写、自动纠错、拼写检查——不关的话系统会替用户把词拼对，功能就废了。
  `submitLabel(.done)` + `onSubmit` 直接提交，键盘上敲回车即可。
- `.revealed` 相位：显示正确单词 + 音标 + 释义 + 「你写的：xxx」（写错时才显示），
  顶部复用既有的 toast 浮出 `✅ 认识 / ⚠️ 模糊 / ❌ 不认识`。

### 底部控件

- 听写 `.input`：三档评分按钮不出现，代之以一个「确定」主按钮。
- 听写 `.revealed`：底部只剩播放条（自动前进，不需要用户再点）。
- 只听模式：完全维持现状（翻卡后出三档评分）。

播放条（上一个/连播/下一个）在两种模式下都常驻不变。

## 五、验证

**判定逻辑**：项目当前没有 iOS 单测 target，而给一个用
`PBXFileSystemSynchronizedRootGroup` 组织的工程手工加 target 需要改 `project.pbxproj`，
风险与收益不成比例。改为用 `swiftc` 直接编译**真实源文件**跑断言：

```bash
./ios/Tests/run-dictation-judge-tests.sh
```

脚本落在 `ios/Tests/`（在 Xcode 同步组 `WordLens` 之外，不会被拉进 App target），
入口 `ios/Tests/run-dictation-judge-tests.sh`，共 30 条断言，覆盖：完全一致、大小写、
连字符/空格三种写法、错 1 字母、错 2 字母、各长度档的边界（`it`/`cat`/`card` 必须判
不认识，`hous`/`boundry` 判模糊）、空输入、完全不同的词、`normalize` 与 `levenshtein`
本身。

**端到端**：Xcode 构建 + 真机手测：
1. 顶部开关切到听写 → 卡片变成填写框，看不到单词
2. 连播下读完 3 遍 → 输入框自动聚焦，连播停在这个词不往下走
3. 写对 → 亮答案显示"认识" → 1.5s 后自动进下一词并继续连播
4. 写错 1 个字母 → 判"模糊"；乱写 → 判"不认识"
5. 切回只听模式 → 行为跟现在完全一致（回归）

## 六、不做的事（YAGNI）

- 不做"重试/再听一遍"按钮：想再听点卡片上的小喇叭即可。
- 不做听写历史/正确率统计：SM-2 状态已经承载了这个信息。
- 不做逐字母提示：确认过「什么都不留」。
