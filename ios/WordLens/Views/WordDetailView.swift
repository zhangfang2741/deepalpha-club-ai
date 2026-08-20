// Views/WordDetailView.swift
import SwiftUI

/// 单词详情：纯查看页，只读。
///
/// 这里曾经有一组三档评分按钮，直接调 review 接口推进 SM-2。问题是详情页没有
/// "下一张卡"的概念，同一个词能被反复评，复习间隔/连续次数会被无限推进——当时
/// 靠一个「本次页面会话只能评一次」的锁勉强挡着，但那只是缓解，不是解决：退出
/// 重进照样能接着评。
///
/// 现在评分只发生在首页的复习流里（评完即从队列移除、自动翻到下一词，天然
/// 一词一次），路径唯一、SM-2 状态可控。详情页回归它本来的职责：把一个词的
/// 释义、词根、例句和复习状态摊开给你看。
struct WordDetailView: View {
    let word: VocabularyWord

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            ScrollView {
                VStack(spacing: 20) {
                    VStack(spacing: 8) {
                        HStack {
                            Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                            PronounceButton(word: word.word)
                        }
                        Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)
                        Text("\(word.partOfSpeech) \(word.definitionZh)")
                            .foregroundStyle(Theme.textPrimary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()

                    VStack(alignment: .leading, spacing: 8) {
                        detailRow("状态", statusLabel)
                        detailRow("连续认识次数", "\(word.repetitionCount)")
                        detailRow("复习间隔", "\(word.intervalDays) 天")
                        detailRow("下次复习", nextReviewLabel)
                    }
                    .padding()
                    .background(Theme.surface)
                    .clipShape(.rect(cornerRadius: 12))

                    if !word.etymology.isEmpty || !word.exampleSentence.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            if !word.etymology.isEmpty {
                                detailBlock("词根", word.etymology)
                            }
                            if !word.exampleSentence.isEmpty {
                                detailBlock("例句", word.exampleSentence)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Theme.surface)
                        .clipShape(.rect(cornerRadius: 12))
                    }

                    Text("想复习这个词就去学习页，评分只在那里进行")
                        .font(.footnote)
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.top, 4)
                }
                .padding()
            }
        }
        .navigationTitle("单词详情")
        .navigationBarTitleDisplayMode(.inline)
        // 进入详情时按「自动发音」设置决定是否朗读。
        .task { Pronouncer.shared.speakIfAutoplayEnabled(word.word) }
    }

    private var statusLabel: String {
        switch word.status {
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
        guard let date = Self.parseBackendDate(word.nextReviewAt) else { return word.nextReviewAt }
        if date <= Date() { return L("待复习") }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: Localized.language().localeIdentifier)
        formatter.dateFormat = L("M月d日 HH:mm")
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
}
