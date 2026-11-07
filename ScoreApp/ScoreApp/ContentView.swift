//
//  ContentView.swift
//  ScoreApp
//
//  主界面：毛玻璃顶栏 + 查询 + 判卷进度 + 成绩表格 + 图表
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
                    // 标题区
                    Text("期中 · 查分")
                        .font(.docTitle)
                        .foregroundStyle(isDark ? Color(red: 0xfa/255, green: 0xfa/255, blue: 0xfa/255) : .docFg)
                    Text("输入姓名查询初一 / 初二 / 初三期中成绩、排名与判卷进度")
                        .font(.docBody)
                        .foregroundStyle(.docMuted)
                        .padding(.top, 6)

                    // 查询栏
                    HStack(spacing: 8) {
                        TextField("输入学生姓名，如：杨栋程 / 陈若琳", text: $queryText)
                            .textFieldStyle(.plain)
                            .font(.docBody)
                            .frame(height: UAPI.controlHeight)
                            .padding(.horizontal, 14)
                            .background(isDark ? Color(red: 0x09/255, green: 0x09/255, blue: 0x0b/255) : .white)
                            .clipShape(RoundedRectangle(cornerRadius: UAPI.controlRadius, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: UAPI.controlRadius, style: .continuous)
                                    .strokeBorder(isDark ? Color.white.opacity(0.08) : .docLine, lineWidth: 1)
                            )
                            .onSubmit { runQuery() }

                        Button(action: runQuery) {
                            if isLoading {
                                ProgressView().tint(.white)
                                    .frame(width: 60, height: UAPI.controlHeight)
                            } else {
                                Text("查询")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundStyle(.white)
                                    .frame(width: 60, height: UAPI.controlHeight)
                            }
                        }
                        .background(.uapiTeal)
                        .clipShape(RoundedRectangle(cornerRadius: UAPI.controlRadius, style: .continuous))
                        .disabled(isLoading)
                    }
                    .padding(.top, 24)

                    if let message {
                        Text(message)
                            .font(.docSmall)
                            .foregroundStyle(message!.contains("未") ? Color.red : .docMuted)
                            .padding(.top, 8)
                    }

                    // 成绩结果
                    if let result {
                        ForEach(result, id: \.studentNum + \.grade) { r in
                            resultCard(r)
                        }
                    }

                    // 判卷进度
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

    // MARK: - 查询

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

    // MARK: - 进度

    private func loadProgress() async {
        do {
            progress = try await ScoreAPI.shared.progress()
        } catch { }
    }

    // MARK: - 结果卡片

    @ViewBuilder
    private func resultCard(_ r: QueryResult) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(r.name).font(.system(size: 20, weight: .semibold))
                        Text(r.grade)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(.uapiTeal)
                            .padding(.horizontal, 8).padding(.vertical, 2)
                            .background(Color.uapiTeal.opacity(0.12))
                            .clipShape(Capsule())
                    }
                    Text("\(r.className) · 学号 \(r.studentNum)")
                        .font(.docSmall)
                        .foregroundStyle(.docMuted)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(r.total.formatted(.number.precision(.fractionLength(1))))")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundStyle(.uapiTeal)
                        + Text("/\(Int(r.totalFull))")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(.docFaint)
                    Text("得分率 \(Int(r.rate))%")
                        .font(.docCaption)
                        .foregroundStyle(.docMuted)
                }
            }

            // 表格
            VStack(spacing: 0) {
                HStack {
                    Text("科目").frame(maxWidth: .infinity, alignment: .leading)
                    Text("分数").frame(width: 56, alignment: .trailing)
                    Text("满分").frame(width: 48, alignment: .trailing)
                    Text("年级").frame(width: 48, alignment: .trailing)
                    Text("班级").frame(width: 48, alignment: .trailing)
                    Text("班均").frame(width: 56, alignment: .trailing)
                }
                .font(.docSmall).foregroundStyle(.docMuted)
                .padding(.vertical, 8)

                ForEach(r.courses) { c in
                    HStack {
                        Text(c.course).frame(maxWidth: .infinity, alignment: .leading)
                        Text("\(c.score.formatted(.number.precision(.fractionLength(1))))").frame(width: 56, alignment: .trailing)
                        Text("\(Int(c.full))").frame(width: 48, alignment: .trailing)
                        Text("\(c.examRank)").frame(width: 48, alignment: .trailing)
                        Text("\(c.classRank)").frame(width: 48, alignment: .trailing)
                        Text("\(c.avg.formatted(.number.precision(.fractionLength(1))))").frame(width: 56, alignment: .trailing)
                    }
                    .font(.system(size: 13.5))
                    .padding(.vertical, 8)
                    .overlay(alignment: .bottom) { Divider().opacity(0.5) }
                }

                HStack {
                    Text("合计").font(.system(size: 13.5, weight: .semibold))
                    Spacer()
                    Text("\(r.total.formatted(.number.precision(.fractionLength(1))))").font(.system(size: 13.5, weight: .semibold))
                    Text("\(Int(r.totalFull))").font(.system(size: 13.5, weight: .semibold)).foregroundStyle(.docMuted)
                }
                .padding(.vertical, 8)
            }

            // 图表
            BarChart(courses: r.courses)
            RadarChart(courses: r.courses)
        }
        .padding(18)
        .background(isDark ? Color.white.opacity(0.04) : Color.white)
        .clipShape(RoundedRectangle(cornerRadius: UAPI.cardRadius, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: UAPI.cardRadius, style: .continuous).strokeBorder(.docLine, lineWidth: 1))
        .padding(.top, 20)
    }

    // MARK: - 进度区

    private var progressSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("判卷进度")
                .font(.docHeading)
            ForEach(progress) { g in
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text(g.grade).font(.system(size: 16, weight: .semibold))
                        Spacer()
                        Text("\(g.overall)%").font(.system(size: 20, weight: .bold)).foregroundStyle(.uapiTeal)
                        Text("整体完成度").font(.docCaption).foregroundStyle(.docFaint)
                    }
                    ForEach(g.subjects) { s in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text("\(s.name)").font(.system(size: 13, weight: .medium))
                                Text("满分 \(Int(s.full))").font(.docCaption).foregroundStyle(.docFaint)
                                Spacer()
                                Text("\(Int(s.rate))%").font(.docSmall).foregroundStyle(.docMuted)
                                MarkBadge(status: .from(rate: s.rate, entrust: s.entrust, answerStatus: s.answerStatus))
                            }
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    Capsule().fill(.docLine).frame(height: 8)
                                    Capsule()
                                        .fill(LinearGradient(colors: [.uapiTeal, .uapiTeal2], startPoint: .leading, endPoint: .trailing))
                                        .frame(width: geo.size.width * CGFloat(s.rate) / 100, height: 8)
                                }
                            }
                            .frame(height: 8)
                        }
                    }
                }
                .padding(.bottom, 8)
            }
        }
        .padding(.top, 40)
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
