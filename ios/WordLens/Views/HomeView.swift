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

                // 自定义分组筛选：跟状态磁贴同级，用户点 chips 跟点状态磁贴是
                // 同一类动作（筛选）。chips 用流式排版避免多了挤换行。
                if !playlistVM.playlists.isEmpty {
                    playlistFilterChips
                }

                TextField("搜索单词", text: $listVM.searchQuery)
                    .padding(10)
                    .background(Theme.surface)
                    .foregroundStyle(Theme.textPrimary)
                    .clipShape(.rect(cornerRadius: 8))
                    .onSubmit { Task { await listVM.load() } }

                // 生词库列表按字母分 Section 展示，需要用 List 自己独立滚动，
                // 不能再跟上面的卡片一起塞进一个大 ScrollView。
                WordListView(viewModel: listVM, onRefresh: refreshAll)
            }
            .padding(.horizontal)
            .padding(.top)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("生词库")
            .sheet(isPresented: $showPlaylistManager) {
                PlaylistManagerView(viewModel: playlistVM)
            }
            .task { await refreshAll() }
            .onChange(of: nav.vocabularyDataVersion) { _, _ in
                Task { await refreshAll() }
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
                Task {
                    await refreshAll()
                    try? await Task.sleep(for: .seconds(2.5))
                    withAnimation { nav.clearHighlight() }
                }
            }
        }
    }

    private func refreshAll() async {
        await listVM.load()
        await playlistVM.load()
    }

    /// 自定义分组的筛选 chips + 「全部」reset + 「分组管理」入口。
    ///
    /// 全部的"清除筛选"已经写在顶部第一个状态磁贴里（全量）——chips 这行不需要
    /// 再重复一个"全部"。只在最右放「分组管理」，引导用户去编辑分组。
    /// 自定义分组的筛选 chips + 「分组管理」入口。
    ///
    /// 跟状态磁贴**互斥**：磁贴是按"状态"过滤，chips 是按"分组"过滤——
    /// 两种过滤叠加在产品上没有意义（用户通常想知道"这个分组里的生词"或者
    /// "我不认识的词"，而不是两者的交集）。点 chips 会清掉状态过滤，反之
    /// 亦然，跟"全部"的隐含语义一致：磁贴默认就是「全量」，跟 chips 互斥
    /// 反而让"全选/全清"这条路径只需一次点击。
    private var playlistFilterChips: some View {
        FlowLayout(spacing: 8, lineSpacing: 8) {
            ForEach(playlistVM.playlists) { playlist in
                playlistChip(label: playlist.name, count: playlist.wordCount,
                             isSelected: listVM.filterPlaylistID == playlist.id) {
                    let next: String? = listVM.filterPlaylistID == playlist.id ? nil : playlist.id
                    listVM.filterPlaylistID = next
                    // 互斥：选了自定义分组，状态磁贴就该让位。点 chips 之前可能
                    // 选了某个状态，先清掉，免得两边都生效、列表按交集过滤，
                    // 用户又看到跟之前一样的"看着不工作"问题。
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
                Text("分组管理")
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
        .accessibilityLabel("分组管理")
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
        .accessibilityLabel("\(label)，\(count) 个")
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }

    /// 统计数字本身就是筛选入口。
    ///
    /// 计数永远按全量 allWords 算，跟自定义分组的 chips 互不联动——
    /// 状态磁贴和 chips 是两种正交的过滤维度，**互斥**而非叠加：点状态磁贴
    /// 会清掉当前的 chips 选择，反过来点 chips 也会清掉状态选择。状态磁贴
    /// 上的数字始终是"我生词库里的真实分布"，不会被 chips 牵着走。
    private var statsRow: some View {
        let words = listVM.allWords
        let unknownCount = words.filter { $0.status == "new" }.count
        let fuzzyCount = words.filter { $0.status == "fuzzy" }.count
        let knownCount = words.filter { $0.status == "known" }.count
        return HStack(spacing: 12) {
            statTile("全部", words.count, Theme.textPrimary, isSelected: listVM.filterStatus == nil) {
                listVM.filterStatus = nil
                // 状态选回 nil 时同步清掉 chips，跟"全选"语义一致
                clearPlaylistFilter()
            }
            statTile("不认识", unknownCount, Theme.unknown, isSelected: listVM.filterStatus == "new") {
                listVM.filterStatus = listVM.filterStatus == "new" ? nil : "new"
                // 选了具体状态时同步清掉 chips，让 chips 给状态让位
                if listVM.filterStatus != nil { clearPlaylistFilter() }
            }
            statTile("模糊", fuzzyCount, Theme.fuzzy, isSelected: listVM.filterStatus == "fuzzy") {
                listVM.filterStatus = listVM.filterStatus == "fuzzy" ? nil : "fuzzy"
                if listVM.filterStatus != nil { clearPlaylistFilter() }
            }
            statTile("认识", knownCount, Theme.known, isSelected: listVM.filterStatus == "known") {
                listVM.filterStatus = listVM.filterStatus == "known" ? nil : "known"
                if listVM.filterStatus != nil { clearPlaylistFilter() }
            }
        }
    }

    /// 状态磁贴互斥用：清掉自定义分组筛选 + 缓存。
    /// 单独抽出来是因为 chips 那边的对称操作里也得调用一次。
    private func clearPlaylistFilter() {
        guard listVM.filterPlaylistID != nil else { return }
        listVM.filterPlaylistID = nil
        listVM.playlistWords = []
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
        .accessibilityLabel("\(label)，\(count) 个")
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }
}
