import SwiftUI
import DeepAlphaBaZiCore

/// 新用户填生辰：日期限定 1900年~今天，时辰可标"不确定"，城市限定后端支持的38个。
struct BirthInfoFormView: View {
    @Environment(BaziViewModel.self) private var baziVM

    @State private var birthDate = Date()
    @State private var birthTime = Date()
    @State private var hourUnknown = false
    @State private var birthCity = BaziFormatting.supportedCities[0]
    @State private var gender = "male"

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
                    ForEach(BaziFormatting.supportedCities, id: \.self) { city in
                        Text(city).tag(city)
                    }
                }
                Picker("性别", selection: $gender) {
                    Text("男").tag("male")
                    Text("女").tag("female")
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
                .disabled(baziVM.isSubmittingBirthInfo)
            }
        }
        .navigationTitle("填写生辰")
    }

    private func submit() {
        let dateString = BaziFormatting.birthDateString(from: birthDate)
        let timeString = hourUnknown ? nil : BaziFormatting.birthTimeString(from: birthTime)
        Task {
            await baziVM.submitBirthInfo(
                birthDate: dateString, birthTime: timeString,
                birthCity: birthCity, gender: gender)
        }
    }
}
