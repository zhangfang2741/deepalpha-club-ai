# WordLens 设置页重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 将 WordLens 的 Tab 4 设置页重构为清晰的原生 iOS 设置首页，并把修改密码移动到独立的“账户与安全”二级页面。

**架构：** 保留现有 `SettingsViewModel` 和 `AuthService`，让 `SettingsView` 只负责个人资料展示、偏好导航和账户操作。新增 `AccountSecurityView` 复用设置 ViewModel 中的密码修改状态和方法；发音设置通过同一导航栈 push 进入，删除复习首页的重复快捷入口。

**技术栈：** SwiftUI、现有 `Theme` 主题、现有 `SettingsViewModel`、iOS `Form`/`Section`/`NavigationLink`。

## 全局约束

- 所有用户可见文案和新增代码注释使用中文。
- Swift 变量名、函数名和类型名保持英文。
- 不新增第三方依赖，不改变后端密码接口。
- 延续现有深色主题和 `Theme` 配色。
- 所有密码输入和提交状态必须支持 Dynamic Type、VoiceOver，并在提交期间防止重复操作。
- 保留工作区中与本任务无关的 `.DS_Store` 和 `ReviewCardFlipPrototypes.swift`。

---

### 任务 1：创建账户与安全二级页面

**文件：**
- 创建：`ios/WordLens/Views/AccountSecurityView.swift`
- 复用：`ios/WordLens/ViewModels/SettingsViewModel.swift`

**接口：**
- 输入：`@ObservedObject var viewModel: SettingsViewModel`
- 输出：独立导航页面 `AccountSecurityView`，复用 `changePassword(oldPassword:newPassword:) async -> Bool`。

- [ ] 将现有设置页中的三个 `SecureField`、密码规则、错误/成功消息和提交按钮移动到 `AccountSecurityView`。
- [ ] 保持密码校验规则：原密码非空、新密码至少 8 位、包含字母和数字、两次输入一致。
- [ ] 提交期间禁用三个输入框和提交按钮，显示进度状态；成功时清空字段，失败时保留输入并显示错误。
- [ ] 使用 `Form` 和 `Section`，为规则图标提供文字无障碍标签，页面标题为“账户与安全”。
- [ ] 用 `git diff --check` 检查新增文件格式。

### 任务 2：重构设置首页

**文件：**
- 修改：`ios/WordLens/Views/SettingsView.swift`

**接口：**
- 保留：`SettingsView`、现有个人资料加载和 `AuthViewModel.logout()`。
- 新增导航：`NavigationLink` 到 `PronunciationSettingsView` 和 `AccountSecurityView(viewModel: viewModel)`。

- [ ] 删除设置首页的密码字段、密码规则、提交状态和密码校验计算属性。
- [ ] 账户概览保留邮箱和注册日期，增加用户图标；加载中保留稳定布局，失败时提供简短错误信息和重试入口。
- [ ] 新增“偏好设置”区域，通过带 `speaker.wave.2` 图标的导航行进入发音设置。
- [ ] 新增“账户与安全”导航行，把修改密码降级为二级页面入口。
- [ ] 保留底部低强调的“退出登录”危险操作。
- [ ] 继续使用现有 `Theme.background`、`Theme.surface` 和系统 `Form`，确保长邮箱不挤压相邻内容。

### 任务 3：移除复习页重复的发音设置入口

**文件：**
- 修改：`ios/WordLens/Views/ReviewCardView.swift`

- [ ] 先确认当前 toolbar、sheet 状态和其他并行改动，只删除 `showPronunciationSettings` 状态、旧 toolbar 按钮及对应 sheet。
- [ ] 保留复习页现有卡片、自动播放和 FAB 行为，不调整无关布局。
- [ ] 用 `rg` 确认复习页不再引用 `PronunciationSettingsView` 或旧状态。

### 任务 4：构建与界面回归验证

**文件：**
- 检查：`ios/WordLens/Views/SettingsView.swift`
- 检查：`ios/WordLens/Views/AccountSecurityView.swift`
- 检查：`ios/WordLens/Views/PronunciationSettingsView.swift`
- 检查：`ios/WordLens/Views/ReviewCardView.swift`

- [ ] 执行 `git diff --check`，确认没有空白错误。
- [ ] 执行 `xcodebuild -project ios/WordLens.xcodeproj -scheme WordLens -destination 'platform=iOS Simulator,name=iPhone 17' build`。
- [ ] 检查设置首页不包含密码输入控件，且存在“发音设置”和“账户与安全”导航入口。
- [ ] 检查复习页不再显示发音设置 toolbar 按钮。
- [ ] 在可用时启动 iPhone 17 模拟器，检查设置首页和账户与安全页在较大 Dynamic Type 下无重叠。
- [ ] 汇总构建结果、未能执行的验证项和工作区变更，不自动 push。
