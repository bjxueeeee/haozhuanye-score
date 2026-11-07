//
//  Theme.swift
//  ScoreApp
//
//  UI 主题：混合 UAPI（Teal 圆角）+ QQ 文档站（白底窄栏细线）
//  iOS 26 原生 SwiftUI
//

import SwiftUI

// MARK: - 颜色（UAPI Teal + QQ 文档站 Zinc）
extension Color {
    /// UAPI 主操作色（青绿）
    static let uapiTeal      = Color(red: 0x0d/255, green: 0x94/255, blue: 0x88/255)
    /// UAPI 渐变辅助色
    static let uapiTeal2     = Color(red: 0x14/255, green: 0xb8/255, blue: 0xa6/255)

    /// QQ 文档站主文字（近黑）
    static let docFg         = Color(red: 0x18/255, green: 0x18/255, blue: 0x1b/255)
    /// QQ 文档站次级文字
    static let docMuted      = Color(red: 0x71/255, green: 0x71/255, blue: 0x7a/255)
    /// QQ 文档站弱文字
    static let docFaint      = Color(red: 0xa1/255, green: 0xa1/255, blue: 0xaa/255)
    /// QQ 文档站细线（低对比）
    static let docLine       = Color(red: 0x18/255, green: 0x18/255, blue: 0x1b/255).opacity(0.07)
    /// 行内代码淡灰底
    static let docCodeBg     = Color(red: 0x18/255, green: 0x18/255, blue: 0x1b/255).opacity(0.035)

    /// 判卷徽章
    static let badgeDoneBg   = Color.uapiTeal.opacity(0.12)
    static let badgeDoingBg  = Color(red: 0x31/255, green: 0x7c/255, blue: 0xfe/255).opacity(0.10)
    static let badgeStuckBg  = Color(red: 0x18/255, green: 0x18/255, blue: 0x1b/255).opacity(0.06)
    static let badgeSlowBg   = Color(red: 0xea/255, green: 0xb3/255, blue: 0x08/255).opacity(0.12)
}

// MARK: - 圆角 / 尺寸（UAPI）
enum UAPI {
    /// 按钮 / 输入框圆角
    static let controlRadius: CGFloat = 12
    /// 卡片圆角
    static let cardRadius: CGFloat = 14
    /// 徽章圆角
    static let badgeRadius: CGFloat = 6
    /// 控件高度
    static let controlHeight: CGFloat = 44
}

// MARK: - 字体（QQ 文档站：Inter / Noto Sans SC 回退）
extension Font {
    static let docTitle  = Font.system(size: 32, weight: .semibold)
    static let docHeading = Font.system(size: 20, weight: .semibold)
    static let docBody   = Font.system(size: 14.5)
    static let docSmall  = Font.system(size: 12.5)
    static let docCaption = Font.system(size: 12)
    static let docCode   = Font.system(size: 12.5, design: .monospaced)
}

// MARK: - 判卷状态徽章
enum MarkStatus {
    case done, doing, stuck, slow

    var label: String {
        switch self {
        case .done:  return "已判完"
        case .doing: return "阅卷中"
        case .stuck: return "待分配"
        case .slow:  return "识别中"
        }
    }

    var fg: Color {
        switch self {
        case .done:  return .uapiTeal
        case .doing: return Color(red: 0x31/255, green: 0x7c/255, blue: 0xfe/255)
        case .stuck: return .docMuted
        case .slow:  return Color(red: 0xb4/255, green: 0x53/255, blue: 0x09/255)
        }
    }

    var bg: Color {
        switch self {
        case .done:  return .badgeDoneBg
        case .doing: return .badgeDoingBg
        case .stuck: return .badgeStuckBg
        case .slow:  return .badgeSlowBg
        }
    }

    static func from(rate: Int, entrust: Int?, answerStatus: Int?) -> MarkStatus {
        if rate >= 75 { return .done }
        if rate >= 45 { return .doing }
        if entrust == 1 { return .stuck }
        if answerStatus == 0 { return .slow }
        return .stuck
    }
}
