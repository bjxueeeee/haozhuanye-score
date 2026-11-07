//
//  Charts.swift
//  ScoreApp
//

import SwiftUI

// MARK: - 条形对比图

struct BarChart: View {
    let courses: [StudentScore]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(courses, id: \.id) { c in
                HStack(spacing: 10) {
                    Text(c.course)
                        .font(.system(size: 12.5))
                        .foregroundStyle(Color.docFg)
                        .frame(width: 56, alignment: .leading)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 5).fill(Color.docCodeBg)
                            RoundedRectangle(cornerRadius: 5)
                                .fill(LinearGradient(colors: [Color.uapiTeal, Color.uapiTeal2], startPoint: .leading, endPoint: .trailing))
                                .frame(width: geo.size.width * CGFloat(min(c.rate / 100, 1)))
                            Rectangle()
                                .fill(Color.docFg)
                                .frame(width: 2)
                                .offset(x: geo.size.width * CGFloat(min(c.avgRate / 100, 1)) - 1)
                        }
                    }
                    .frame(height: 16)
                    Text("\(c.score.formatted(.number.precision(.fractionLength(1))))/\(Int(c.full))")
                        .font(.system(size: 12.5))
                        .foregroundStyle(Color.docMuted)
                        .frame(width: 64, alignment: .trailing)
                }
            }
            HStack(spacing: 16) {
                legend(color: Color.uapiTeal, label: "学生得分率")
                legend(color: Color.docFg, label: "班均得分率")
            }
            .font(.docCaption).foregroundStyle(Color.docMuted)
        }
        .padding(.top, 4)
    }

    private func legend(color: Color, label: String) -> some View {
        HStack(spacing: 5) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 10, height: 10)
            Text(label)
        }
    }
}

// MARK: - 雷达图

struct RadarChart: View {
    let courses: [StudentScore]

    var body: some View {
        GeometryReader { geo in
            let size = min(geo.size.width, 240)
            let center = CGPoint(x: size / 2, y: size / 2)
            let radius = size / 2 - 26
            let n = max(courses.count, 3)

            ZStack {
                ForEach(Array(1...4), id: \.self) { level in
                    polygonPath(center: center, radius: radius * CGFloat(level) / 4, n: n)
                        .stroke(Color.gray.opacity(0.15), lineWidth: 1)
                }
                ForEach(Array(0..<n), id: \.self) { i in
                    let p = point(center: center, radius: radius, index: i, n: n)
                    Path { path in
                        path.move(to: center)
                        path.addLine(to: p)
                    }
                    .stroke(Color.gray.opacity(0.15), lineWidth: 1)
                }
                polygonPath(center: center, radius: radius, n: n, ratios: courses.map { $0.avgRate / 100 })
                    .stroke(Color.docFg, style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
                    .opacity(0.55)
                polygonPath(center: center, radius: radius, n: n, ratios: courses.map { min($0.rate / 100, 1) })
                    .fill(Color.uapiTeal.opacity(0.22))
                polygonPath(center: center, radius: radius, n: n, ratios: courses.map { min($0.rate / 100, 1) })
                    .stroke(Color.uapiTeal, lineWidth: 2)
                ForEach(Array(0..<n), id: \.self) { i in
                    let p = point(center: center, radius: radius + 18, index: i, n: n)
                    Text(courses[i].course)
                        .font(.system(size: 10.5))
                        .foregroundStyle(Color.docMuted)
                        .position(p)
                }
            }
            .frame(width: size, height: size)
        }
        .frame(height: 240)
        .overlay(alignment: .bottom) {
            Text("各科得分率（绿=学生 · 虚线=班均）")
                .font(.system(size: 11))
                .foregroundStyle(Color.docFaint)
        }
    }

    private func point(center: CGPoint, radius: CGFloat, index: Int, n: Int) -> CGPoint {
        let angle = (Double(index) * 360.0 / Double(n) - 90) * .pi / 180
        return CGPoint(x: center.x + radius * CGFloat(cos(angle)),
                       y: center.y + radius * CGFloat(sin(angle)))
    }

    private func polygonPath(center: CGPoint, radius: CGFloat, n: Int, ratios: [Double]? = nil) -> Path {
        Path { path in
            for i in 0..<n {
                let ratio = ratios.map { min(max($0[i], 0), 1) } ?? 1
                let p = point(center: center, radius: radius * CGFloat(ratio), index: i, n: n)
                if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
            }
            path.closeSubpath()
        }
    }
}

private extension StudentScore {
    var avgRate: Double { full > 0 ? avg / full * 100 : 0 }
}
