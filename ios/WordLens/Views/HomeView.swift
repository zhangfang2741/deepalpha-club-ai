// Views/HomeView.swift
import SwiftUI

struct HomeView: View {
    @StateObject private var listVM = WordListViewModel()
    /// 分组管理：新建/改名/改词表/删除。放在生词库而不是首页的切换分组页——
    /// 换组是一秒钟的高频动作，管理是低频的编辑动作，混在一起互相干扰；而且
    /// 「往分组里放哪些词」本来就是在生词库里挑词，跟这里同源。
    @StateObject private var playlistVM = PlaylistViewModel()
    @State private var showPlaylistManager = false
    @EnvironmentObject var nav: AppNavigationState

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                statsRow

                // 自定义分组筛选：已有分组时显示筛选 chips；「分组管理」始终保留，
                // 否则新用户正因为没有分组，反而看不到创建第一个分组的入口。
                playlistFilterChips

                TextField(L("搜索单词"), text: $listVM.searchQuery)
                    .padding(10)
                    .background(Theme.surface)
                    .foregroundStyle(Theme.textPrimary)
                    .clipShape(.rect(cornerRadius: 8))
                    .onSubmit { Task { await listVM.load() } }

                // 生词库列表按字母分 Section 展示，需要用 List 自己独立滚动，
                // 不能再跟上面的卡片一起塞进一个大 ScrollView。
                WordListView(viewModel: listVM) {
                    await refreshAll(forcePlaylists: true)
                }
            }
            .padding(.horizontal)
            .padding(.top)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle(L("生词库"))
            .sheet(isPresented: $showPlaylistManager) {
                PlaylistManagerView(viewModel: playlistVM)
            }
            .task { await refreshAll() }
            .onChange(of: nav.vocabularyDataVersion) { _, _ in
                Task { await refreshAll(forcePlaylists: true) }
            }
            // 切回「生词库」tab 时刷新统计：首页复习卡评分走的是独立的
            // ReviewViewModel，不会碰这里的 listVM、也不适合 bump
            // vocabularyDataVersion（那会连带把复习卡的队列进度重置）。所以
            // 靠"切回本 tab 就重拉一次"来保证顶部各状态数字跟最新复习结果一致。
            .onChange(of: nav.selectedTab) { _, newTab in
                guard newTab == .vocabulary else { return }
                Task { await refreshAll() }
            }
            .onChange(of: nav.highlightedWordIDs) { _, ids in
                guard !ids.isEmpty else { return }
                // 从拍照页跳过来时新词肯定是"不认识"状态，之前如果筛选停在别的状态
                // 上会把新词全部挡住，先清掉筛选保证能看见；listVM 是这个 view 自己
                // 的实例，跟拍照页那边完全独立，得重新拉一次才能看到刚加的词。
                listVM.filterStatus = nil
                listVM.clearPlaylistFilter()
                Task {
                    await refreshAll()
                    try? await Task.sleep(for: .seconds(2.5))
                    withAnimation { nav.clearHighlight() }
                }
            }
        }
    }

    private func refreshAll(forcePlaylists: Bool = false) async {
        // 生词列表、统计和自定义分组没有依赖关系，并行加载。分组不再排在完整
        // 生词列表之后，打开管理页时通常已经有缓存可直接展示。
        async let wordsLoad: Void = listVM.load()
        async let playlistLoad: Void = playlistVM.load(forcePlaylists: forcePlaylists)
        _ = await (wordsLoad, playlistLoad)
    }

    /// 自定义分组的筛选 chips + 「分组管理」入口。
    ///
    /// 跟状态磁贴**互斥**：状态（不认识/模糊/认识）和自定义分组是两种正交
    /// 过滤维度，叠加没产品意义。点 chips 之前如果选了状态，先清掉，免得两边
    /// 都生效、列表按交集过滤。
    private var playlistFilterChips: some View {
        FlowLayout(spacing: 8, lineSpacing: 8) {
            ForEach(playlistVM.playlists) { playlist in
                playlistChip(label: playlist.name, count: playlist.wordCount,
                             isSelected: listVM.filterPlaylistID == playlist.id) {
                    let next: String? = listVM.filterPlaylistID == playlist.id ? nil : playlist.id
                    listVM.filterPlaylistID = next
                    // 互斥：选了自定义分组就把状态让位
                    if next != nil { listVM.filterStatus = nil }
                    Task { await listVM.loadPlaylistWords(id: next) }
                }
            }
            manageChip
        }
    }

    private var manageChip: some View {
        Button {
            showPlaylistManager = true
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "folder")
                    .font(.caption.weight(.bold))
                Text(L("分组管理"))
                    .font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(Theme.textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Theme.surface)
            .clipShape(.capsule)
            .overlay {
                Capsule().strokeBorder(Theme.border, lineWidth: 1)
            }
        }
        .buttonStyle(.pressable)
        .accessibilityLabel(L("分组管理"))
    }

    private func playlistChip(label: String, count: Int, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(label)
                    .font(.subheadline.weight(isSelected ? .semibold : .regular))
                    .foregroundStyle(isSelected ? Theme.accent : Theme.textPrimary)
                    .lineLimit(1)
                Text("\(count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? Theme.surfaceAlt : Theme.surface)
            .clipShape(.capsule)
            .overlay {
                Capsule().strokeBorder(isSelected ? Theme.accent : Theme.border, lineWidth: 1)
            }
        }
        .buttonStyle(.pressable)
        .accessibilityLabel(L("%@，%lld 个", label, count))
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }

    /// 状态磁贴：认识/模糊/不认识三个，「全部」也是筛选入口。
    ///
    /// 「全部」**只在两组筛选都未选**时显示选中态——它代表的是"什么筛选都没开"
    /// 这个状态，不是"被默认选中"。只要 chips 选中或状态选中，「全部」就
    /// 退化成普通按钮，不再让人误读为"分组 + 全部"两个都在筛。
    ///
    /// 计数永远按全量 allWords 算，跟 chips 互不联动。状态和自定义分组是两种
    /// 正交过滤维度，互斥：选一边就把另一边清掉。
    private var statsRow: some View {
        let words = listVM.allWords
        let unknownCount = words.filter { $0.status == "new" }.count
        let fuzzyCount = words.filter { $0.status == "fuzzy" }.count
        let knownCount = words.filter { $0.status == "known" }.count
        // 三个具体状态磁贴任一被选、或自定义分组被选，「全部」都不应被画上高亮——
        // 它的"选中"语义是"无筛选"，跟具体筛选互斥。
        let isAllHighlighted = listVM.filterStatus == nil && listVM.filterPlaylistID == nil
        return HStack(spacing: 12) {
            statTile(L("全部"), words.count, Theme.textPrimary, isSelected: isAllHighlighted) {
                listVM.filterStatus = nil
                listVM.clearPlaylistFilter()
            }
            statTile(L("不认识"), unknownCount, Theme.unknown, isSelected: listVM.filterStatus == "new") {
                listVM.filterStatus = listVM.filterStatus == "new" ? nil : "new"
                if listVM.filterStatus != nil { listVM.clearPlaylistFilter() }
            }
            statTile(L("模糊"), fuzzyCount, Theme.fuzzy, isSelected: listVM.filterStatus == "fuzzy") {
                listVM.filterStatus = listVM.filterStatus == "fuzzy" ? nil : "fuzzy"
                if listVM.filterStatus != nil { listVM.clearPlaylistFilter() }
            }
            statTile(L("认识"), knownCount, Theme.known, isSelected: listVM.filterStatus == "known") {
                listVM.filterStatus = listVM.filterStatus == "known" ? nil : "known"
                if listVM.filterStatus != nil { listVM.clearPlaylistFilter() }
            }
        }
    }

    private func statTile(_ label: String, _ count: Int, _ color: Color, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Text("\(count)")
                    .font(.title2.bold())
                    .foregroundStyle(color)
                Text(label)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(isSelected ? Theme.surfaceAlt : Theme.surface)
            .clipShape(.rect(cornerRadius: 10))
            .overlay {
                if isSelected {
                    RoundedRectangle(cornerRadius: 10).strokeBorder(color, lineWidth: 1.5)
                }
            }
        }
        .buttonStyle(.pressable)
        .accessibilityLabel(L("%@，%lld 个", label, count))
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }
}
