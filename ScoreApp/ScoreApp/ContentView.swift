//
//  ContentView.swift
//  ScoreApp
//

import SwiftUI

struct ContentView: View {
    @State private var queryText = ""
    @State private var result: [QueryResult]?
    @State private var progress: [GradeProgress] = []
    @State private var message: String?
    @State private var isLoading = false
    @State private var isDark = false

    var body: some View {
        ZStack {
            (isDark ? Color(red: 0x09/255, green: 0x09/255, blue: 0x0b/255) : Color.white)
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    titleSection
                    queryBar
                    if let message {
                        Text(message)
                            .font(.docSmall)
                            .foregroundStyle(message!.contains("未") ? Color.red : Color.docMuted)
                            .padding(.top, 8)
                    }
                    if let result {
                        ForEach(result, id: \.studentNum) { r in
                            ResultCard(result: r)
                        }
                    }
                    if !progress.isEmpty {
                        progressSection
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 16)
                .padding(.bottom, 60)
                .frame(maxWidth: 720, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    isDark.toggle()
                } label: {
                    Image(systemName: isDark ? "sun.max" : "moon")
                }
            }
        }
        .task { await loadProgress() }
    }

    private var titleSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("期中 · 查分").font(.docTitle).foregroundStyle(Color.docFg)
            Text("输入姓名查询初一 / 初二 / 初三期中成绩、排名与判卷进度")
                .font(.docBody).foregroundStyle(Color.docMuted)
        }
    }

    private var queryBar: some View {
        HStack(spacing: 8) {
            TextField("输入学生姓名，如：杨栋程 / 陈若琳", text: $queryText)
                .textFieldStyle(.plain)
                .font(.docBody)
                .frame(height: UAPI.controlHeight)
                .padding(.horizontal, 14)
                .background(isDark ? Color(red: 0x09/255, green: 0x09/255, blue: 0x0b/255) : Color.white)
                .clipShape(RoundedRectangle(cornerRadius: UAPI.controlRadius, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: UAPI.controlRadius, style: .continuous)
                        .strokeBorder(Color.docLine, lineWidth: 1)
                )
                .onSubmit { runQuery() }

            Button(action: runQuery) {
                if isLoading {
                    ProgressView().tint(.white).frame(width: 60, height: UAPI.controlHeight)
                } else {
                    Text("查询").font(.system(size: 14, weight: .medium))
                        .foregroundStyle(.white).frame(width: 60, height: UAPI.controlHeight)
                }
            }
            .background(Color.uapiTeal)
            .clipShape(RoundedRectangle(cornerRadius: UAPI.controlRadius, style: .continuous))
            .disabled(isLoading)
        }
        .padding(.top, 24)
    }

    private var progressSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("判卷进度").font(.docHeading).foregroundStyle(Color.docFg)
            ForEach(progress, id: \.id) { g in
                GradeProgressView(group: g)
            }
        }
        .padding(.top, 40)
    }

    private func runQuery() {
        let name = queryText.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        isLoading = true
        message = "正在查询…"
        Task {
            do {
                let r = try await ScoreAPI.shared.query(name: name)
                result = r
                message = nil
            } catch {
                result = nil
                message = error.localizedDescription
            }
            isLoading = false
        }
    }

    private func loadProgress() async {
        do { progress = try await ScoreAPI.shared.progress() } catch { }
    }
}

// MARK: - 结果卡片（拆分避免类型检查超时）

struct ResultCard: View {
    let result: QueryResult

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ResultHeader(result: result)
            ScoreTable(result: result)
            BarChart(courses: result.courses)
            RadarChart(courses: result.courses)
        }
        .padding(18)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: UAPI.cardRadius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: UAPI.cardRadius, style: .continuous).strokeBorder(Color.docLine, lineWidth: 1))
        .padding(.top, 20)
    }
}

struct ResultHeader: View {
    let result: QueryResult

    var body: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 8) {
                    Text(result.name).font(.system(size: 20, weight: .semibold)).foregroundStyle(Color.docFg)
                    Text(result.grade)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Color.uapiTeal)
                        .padding(.horizontal, 8).padding(.vertical, 2)
                        .background(Color.uapiTeal.opacity(0.12))
                        .clipShape(Capsule())
                }
                Text("\(result.className) · 学号 \(result.studentNum)")
                    .font(.docSmall).foregroundStyle(Color.docMuted)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(result.total.formatted(.number.precision(.fractionLength(1))))")
                    .font(.system(size: 28, weight: .bold)).foregroundStyle(Color.uapiTeal)
                Text("/\(Int(result.totalFull)) · 得分率 \(Int(result.rate))%")
                    .font(.docCaption).foregroundStyle(Color.docMuted)
            }
        }
    }
}

struct ScoreTable: View {
    let result: QueryResult

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("科目").frame(maxWidth: .infinity, alignment: .leading)
                Text("分数").frame(width: 52, alignment: .trailing)
                Text("满分").frame(width: 44, alignment: .trailing)
                Text("年级").frame(width: 44, alignment: .trailing)
                Text("班级").frame(width: 44, alignment: .trailing)
                Text("班均").frame(width: 52, alignment: .trailing)
            }
            .font(.docSmall).foregroundStyle(Color.docMuted).padding(.vertical, 8)

            ForEach(result.courses, id: \.id) { c in
                HStack {
                    Text(c.course).frame(maxWidth: .infinity, alignment: .leading)
                    Text("\(c.score.formatted(.number.precision(.fractionLength(1))))").frame(width: 52, alignment: .trailing)
                    Text("\(Int(c.full))").frame(width: 44, alignment: .trailing)
                    Text("\(c.examRank)").frame(width: 44, alignment: .trailing)
                    Text("\(c.classRank)").frame(width: 44, alignment: .trailing)
                    Text("\(c.avg.formatted(.number.precision(.fractionLength(1))))").frame(width: 52, alignment: .trailing)
                }
                .font(.system(size: 13.5)).foregroundStyle(Color.docFg)
                .padding(.vertical, 8)
                .overlay(alignment: .bottom) { Divider().opacity(0.5) }
            }

            HStack {
                Text("合计").font(.system(size: 13.5, weight: .semibold)).foregroundStyle(Color.docFg)
                Spacer()
                Text("\(result.total.formatted(.number.precision(.fractionLength(1))))")
                    .font(.system(size: 13.5, weight: .semibold)).foregroundStyle(Color.docFg)
                Text("\(Int(result.totalFull))").font(.system(size: 13.5, weight: .semibold)).foregroundStyle(Color.docMuted)
            }
            .padding(.vertical, 8)
        }
    }
}

struct GradeProgressView: View {
    let group: GradeProgress

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(group.grade).font(.system(size: 16, weight: .semibold)).foregroundStyle(Color.docFg)
                Spacer()
                Text("\(group.overall)%").font(.system(size: 20, weight: .bold)).foregroundStyle(Color.uapiTeal)
                Text("整体完成度").font(.docCaption).foregroundStyle(Color.docFaint)
            }
            ForEach(group.subjects, id: \.id) { s in
                SubjectProgressRow(subject: s)
            }
        }
        .padding(.bottom, 8)
    }
}

struct SubjectProgressRow: View {
    let subject: SubjectProgress

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(subject.name).font(.system(size: 13, weight: .medium)).foregroundStyle(Color.docFg)
                Text("满分 \(Int(subject.full))").font(.docCaption).foregroundStyle(Color.docFaint)
                Spacer()
                Text("\(subject.rate)%").font(.docSmall).foregroundStyle(Color.docMuted)
                MarkBadge(status: .from(rate: subject.rate, entrust: subject.entrust, answerStatus: subject.answerStatus))
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.docLine).frame(height: 8)
                    Capsule()
                        .fill(LinearGradient(colors: [Color.uapiTeal, Color.uapiTeal2], startPoint: .leading, endPoint: .trailing))
                        .frame(width: geo.size.width * CGFloat(subject.rate) / 100, height: 8)
                }
            }
            .frame(height: 8)
        }
    }
}

struct MarkBadge: View {
    let status: MarkStatus
    var body: some View {
        Text(status.label)
            .font(.system(size: 11))
            .foregroundStyle(status.fg)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(status.bg)
            .clipShape(Capsule())
    }
}
