import SwiftUI
import DeepAlphaBaZiCore

/// 新用户填生辰：日期限定 1900年~今天，时辰可标"不确定"，城市限定后端支持的38个。
struct BirthInfoFormView: View {
    @Environment(BaziViewModel.self) private var baziVM

    @State private var birthDate = Date()
    @State private var birthTime = Date()
    @State private var hourUnknown = false
    // 城市/性别不给默认选中值——八字排盘对这两项极度敏感(城市决定真太阳时校正，
    // 性别决定大运顺逆排方向)，预选一个具体值会让用户没主动选就静默提交错误数据，
    // 且不会有任何提示。强制用户显式选择，选之前提交按钮保持禁用。
    @State private var birthCity: String?
    @State private var gender: String?

    var body: some View {
        Form {
            Section("生辰信息") {
                DatePicker("出生日期", selection: $birthDate,
                          in: BaziFormatting.minBirthDate...Date(),
                          displayedComponents: .date)
                Toggle("出生时辰不确定", isOn: $hourUnknown)
                if !hourUnknown {
                    DatePicker("出生时间", selection: $birthTime, displayedComponents: .hourAndMinute)
                }
                Picker("出生城市", selection: $birthCity) {
                    Text("请选择").tag(String?.none)
                    ForEach(BaziFormatting.supportedCities, id: \.self) { city in
                        Text(city).tag(String?(city))
                    }
                }
                Picker("性别", selection: $gender) {
                    Text("请选择").tag(String?.none)
                    Text("男").tag(String?("male"))
                    Text("女").tag(String?("female"))
                }
            }

            if let error = baziVM.formError {
                Text(error).foregroundStyle(.red)
            }

            Section {
                Button {
                    submit()
                } label: {
                    if baziVM.isSubmittingBirthInfo {
                        ProgressView()
                    } else {
                        Text("生成我的免费八字报告")
                    }
                }
                .disabled(baziVM.isSubmittingBirthInfo || birthCity == nil || gender == nil)
            }
        }
        .navigationTitle("填写生辰")
    }

    private func submit() {
        guard let birthCity, let gender else { return }
        let dateString = BaziFormatting.birthDateString(from: birthDate)
        let timeString = hourUnknown ? nil : BaziFormatting.birthTimeString(from: birthTime)
        Task {
            await baziVM.submitBirthInfo(
                birthDate: dateString, birthTime: timeString,
                birthCity: birthCity, gender: gender)
        }
    }
}
