// Views/WordDetailView.swift
import SwiftUI

struct WordDetailView: View {
    let word: VocabularyWord
    @ObservedObject var listViewModel: WordListViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var isSubmitting = false
    @State private var submitError: String?
    /// 详情页没有"下一张卡"的概念，跟首页复习卡片（评完自动翻到下一词，同一个
    /// 词天然只能评一次）不一样——如果不额外拦一道，用户能在同一个词上反复点
    /// 评分按钮，每次都是一次真实的 SM-2 提交，复习间隔/连续次数/下次复习时间
    /// 会被无限次推进。这次页面会话里成功提交过一次就锁住，避免误连点。
    @State private var hasSubmittedThisSession = false
    /// 提交评分后用后端返回的最新词刷新详情，避免看到的还是点按钮之前的 status。
    @State private var currentWord: VocabularyWord
    /// 评分后顶部 toast 提示（1.2s 自动消失）——按下立刻给反馈，不等网络回来。
    /// 跟"本次已提交评分，重新进入详情页可再次评估"那条持久文案并存：toast 是
    /// 即时确认（你刚才评了什么），那条是状态提示（这个 session 内不能再评）。
    @State private var confirmationMessage: String?
    @State private var confirmationColor: Color = .clear

    init(word: VocabularyWord, listViewModel: WordListViewModel) {
        self.word = word
        self.listViewModel = listViewModel
        _currentWord = State(initialValue: word)
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.background.ignoresSafeArea()
            ScrollView {
                VStack(spacing: 20) {
                    VStack(spacing: 8) {
                        HStack {
                            Text(currentWord.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                            PronounceButton(word: currentWord.word)
                        }
                        Text("/\(currentWord.phoneticIpa)/").foregroundStyle(Theme.textSecondary)
                        Text("\(currentWord.partOfSpeech) \(currentWord.definitionZh)")
                            .foregroundStyle(Theme.textPrimary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()

                    VStack(alignment: .leading, spacing: 8) {
                        detailRow("状态", statusLabel)
                        detailRow("连续认识次数", "\(currentWord.repetitionCount)")
                        detailRow("复习间隔", "\(currentWord.intervalDays) 天")
                        detailRow("下次复习", nextReviewLabel)
                    }
                    .padding()
                    .background(Theme.surface)
                    .clipShape(.rect(cornerRadius: 12))

                    if !currentWord.etymology.isEmpty || !currentWord.exampleSentence.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            if !currentWord.etymology.isEmpty {
                                detailBlock("词根", currentWord.etymology)
                            }
                            if !currentWord.exampleSentence.isEmpty {
                                detailBlock("例句", currentWord.exampleSentence)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Theme.surface)
                        .clipShape(.rect(cornerRadius: 12))
                    }

                    if let submitError {
                        Text(submitError)
                            .font(.footnote)
                            .foregroundStyle(Theme.unknown)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    if hasSubmittedThisSession {
                        Text("本次已提交评分，重新进入详情页可再次评估")
                            .font(.footnote)
                            .foregroundStyle(Theme.textSecondary)
                    }

                    // 三档评分按钮直接提交到后端 review 接口（和首页复习卡片背面的评分
                    // 用同一套 WordService.submitReview），不在本地假装"复习"——单词
                    // 详情被点击 = 用户想真正评估一下自己认不认识这个词，那就走真的
                    // 评分，更新 status / 下次复习时间。之前的"删除单词"按钮设计错位：
                    // 详情页天然是"评估/学习"的入口，不是"删词"的入口。
                    HStack(spacing: 12) {
                        ratingButton("😵 不认识", Theme.unknown, .unknown)
                        ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                        ratingButton("😊 认识", Theme.known, .known)
                    }
                    .padding(.top, 8)
                }
                .padding()
            }

            // 顶部确认 toast：覆盖在 ScrollView 上，跟外层 ZStack 对齐 .top，
            // 不参与 ScrollView 内容布局。让 Toast 不被滚动遮挡、也不会
            // 跟评分按钮位置冲突（按钮在底部，toast 在顶部）。
            confirmationToast
                .padding(.top, 8)
                .allowsHitTesting(false)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .navigationTitle("单词详情")
        .navigationBarTitleDisplayMode(.inline)
        // 进入详情时按「自动发音」设置决定是否朗读。
        .task { Pronouncer.shared.speakIfAutoplayEnabled(currentWord.word) }
    }

    private var statusLabel: String {
        switch currentWord.status {
        case "known": return "认识"
        case "fuzzy": return "模糊"
        default: return "不认识"
        }
    }

    /// 后端返回的是不带时区的 ISO 8601 字符串（naive UTC，如
    /// "2026-07-26T08:09:11.390968"），直接显示对用户不友好，这里解析成
    /// Date 后按本地时区格式化。微秒为 0 时 Python 的 isoformat() 会省略
    /// 小数部分，所以两种格式都要能解析。
    ///
    /// 新加入的单词 next_review_at 后端直接设成创建时间（意为"立刻可复习"），
    /// 到期未复习的单词同理会停留在过去，这两种情况都按日期显示会显得像是
    /// "过期出错"，所以已到期一律显示「待复习」。
    private var nextReviewLabel: String {
        guard let date = Self.parseBackendDate(currentWord.nextReviewAt) else { return currentWord.nextReviewAt }
        if date <= Date() { return "待复习" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "M月d日 HH:mm"
        return formatter.string(from: date)
    }

    private static func parseBackendDate(_ raw: String) -> Date? {
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(identifier: "UTC")
            formatter.dateFormat = format
            if let date = formatter.date(from: raw) {
                return date
            }
        }
        return nil
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundStyle(Theme.textSecondary)
            Spacer()
            Text(value).foregroundStyle(Theme.textPrimary)
        }
        .font(.subheadline)
    }

    private func detailBlock(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.subheadline).foregroundStyle(Theme.textSecondary)
            Text(value).font(.subheadline).foregroundStyle(Theme.textPrimary)
        }
    }

    /// 跟首页复习卡片评分按钮视觉一致：emoji + 文字，主题色 20% 底，主题色字，
    /// 平分 HStack 水平空间，按下用统一的 .pressable 反馈样式。
    private func ratingButton(_ label: String, _ color: Color, _ rating: ReviewRating) -> some View {
        Button {
            // 1) 立刻震一下——按下瞬间的触觉反馈，不用等网络回来。
            // 2) 立刻浮 toast 告诉用户"已标记为 X"，不等后端确认。提交后端
            //    成功还有"本次已提交评分"持久文案接管，toast 是即时确认。
            // 3) 异步提交评分（按钮也会被 disable 走 progress 视觉反馈）。
            Haptics.rating(rating)
            showConfirmation(label: label, color: color)
            Task { await submit(rating) }
        } label: {
            Text(label)
                .font(.footnote.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(color.opacity(0.2))
                .foregroundStyle(color)
                .clipShape(.rect(cornerRadius: 10))
        }
        .buttonStyle(.pressable)
        .disabled(isSubmitting || hasSubmittedThisSession)
    }

    /// 弹出顶部 toast：emoji + "已标记为 X"。emoji 从按钮 label 里抠，避免再
    /// 维护一份 i18n 映射表。1.2s 后自动清掉；只在 confirmationMessage 还是
    /// 自己设的那条时才清（防止快速连评两档时第一条把第二条刚设的清掉）。
    private func showConfirmation(label: String, color: Color) {
        let stripped = label
            .replacingOccurrences(of: "😵 ", with: "")
            .replacingOccurrences(of: "😐 ", with: "")
            .replacingOccurrences(of: "😊 ", with: "")
        let message = "已标记为\(stripped)"
        confirmationMessage = message
        confirmationColor = color
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(1.2))
            if confirmationMessage == message {
                confirmationMessage = nil
            }
        }
    }

    private var confirmationToast: some View {
        Group {
            if let message = confirmationMessage {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                    Text(message)
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(confirmationColor)
                .clipShape(.capsule)
                .shadow(color: confirmationColor.opacity(0.35), radius: 8, x: 0, y: 3)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.85), value: confirmationMessage)
    }

    /// 提交评分：成功后用后端返回的最新词刷新详情 + 同步给列表 viewModel，
    /// 让用户返回列表时状态点、筛选数字都对得上；同时锁住评分按钮，防止在
    /// 同一次页面停留里反复提交、把 SM-2 状态越点越远。
    private func submit(_ rating: ReviewRating) async {
        isSubmitting = true
        submitError = nil
        defer { isSubmitting = false }
        do {
            let updated = try await WordService.submitReview(wordId: currentWord.id, rating: rating)
            currentWord = updated
            listViewModel.updateWord(updated)
            hasSubmittedThisSession = true
        } catch let error as APIError {
            submitError = error.message
        } catch {
            submitError = "提交失败，请稍后重试"
        }
    }
}