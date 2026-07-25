// Views/WordDetailView.swift
import SwiftUI

struct WordDetailView: View {
    let word: VocabularyWord
    @ObservedObject var listViewModel: WordListViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var isSubmitting = false
    @State private var submitError: String?
    /// 提交评分后用后端返回的最新词刷新详情，避免看到的还是点按钮之前的 status。
    @State private var currentWord: VocabularyWord

    init(word: VocabularyWord, listViewModel: WordListViewModel) {
        self.word = word
        self.listViewModel = listViewModel
        _currentWord = State(initialValue: word)
    }

    var body: some View {
        ZStack {
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
        .disabled(isSubmitting)
    }

    /// 提交评分：成功后用后端返回的最新词刷新详情 + 同步给列表 viewModel，
    /// 让用户返回列表时状态点、筛选数字都对得上。
    private func submit(_ rating: ReviewRating) async {
        isSubmitting = true
        submitError = nil
        defer { isSubmitting = false }
        do {
            let updated = try await WordService.submitReview(wordId: currentWord.id, rating: rating)
            currentWord = updated
            listViewModel.updateWord(updated)
        } catch let error as APIError {
            submitError = error.message
        } catch {
            submitError = "提交失败，请稍后重试"
        }
    }
}