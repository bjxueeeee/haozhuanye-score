# ScoreApp · iOS 26 原生 App —— 打包 IPA 说明

> 这是「好专业查分」的 iOS 26 原生客户端，UI 混合 **UAPI（Teal 圆角）+ QQ 文档站（白底窄栏细线）**。
> 当前源码在 Windows 上生成，**打包需在 macOS + Xcode 上完成**（iOS 无法跨平台编译签名）。

---

## 一、源码结构

```
ScoreApp/
├── ScoreApp/
│   ├── ScoreApp.swift        # 入口（@main）
│   ├── ContentView.swift     # 主界面（查询 + 进度 + 成绩表格 + 图表）
│   ├── Theme.swift           # UI 主题（UAPI Teal + QQ 文档站配色）
│   ├── Crypto.swift          # AES-128-ECB + gzip（CommonCrypto + Compression）
│   ├── API.swift             # 越权拿 token + 查分 + 判卷进度
│   └── Charts.swift          # 条形图 + 雷达图（SwiftUI 自定义绘制）
└── README_打包IPA.md
```

---

## 二、UI 混合规范

| 部分 | 来源 | 具体 |
|---|---|---|
| 主色 Teal `#0d9488` | UAPI | 按钮、进度条、徽章、总分高亮 |
| 圆角 12px / 控件高 44px | UAPI | 输入框、查询按钮 |
| 徽章（已判完/阅卷中/待分配） | UAPI | 判卷状态 |
| 白底、窄栏 max 720px | QQ 文档站 | 正文阅读栏 |
| 低对比细线 `rgba(24,24,27,0.07)` | QQ 文档站 | 表格、卡片边框 |
| 黑灰文字 `#18181b`/`#71717a` | QQ 文档站 | 主/次文字 |
| 毛玻璃顶栏 + 深浅色切换 | QQ 文档站 + UAPI | 顶栏 |

---

## 三、打包步骤（需 Mac + Xcode 16+）

### 1. 创建 Xcode 工程

在 Mac 上新建 iOS App 工程（SwiftUI），将 `ScoreApp/` 下的 6 个 `.swift` 文件拖入工程：

```
Product Name: ScoreApp
Interface: SwiftUI
Language: Swift
Deployment Target: iOS 26.0
```

### 2. 配置 App Transport Security（HTTP/HTTPS 访问）

`Info.plist` 中添加（目标 API 均为 HTTPS，若需调试可放开 HTTP）：

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

### 3. 配置签名

Xcode → Signing & Capabilities → 选择你的 Apple Developer Team（或免费个人签名）。

### 4. Archive 打包

1. 菜单 Product → Scheme → `Edit Scheme` → Run 选 Release；
2. 选择真机设备或 `Any iOS Device (arm64)`；
3. Product → **Archive**；
4. 在 Organizer 中 → **Distribute App** → 选择：
   - App Store Connect（上架）或
   - Ad Hoc / Development（测试分发，需 UDID）或
   - **Release Testing（Export .ipa）**。

### 5. 命令行导出 IPA（可选）

```bash
xcodebuild archive \
  -project ScoreApp.xcodeproj \
  -scheme ScoreApp \
  -archivePath build/ScoreApp.xcarchive \
  -destination "generic/platform=iOS"

xcodebuild -exportArchive \
  -archivePath build/ScoreApp.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath build/
```

---

## 四、核心逻辑说明

### 越权拿教师 token（`API.swift`）

```swift
// getTicket 不校验 token → SSO 换教师 dongniLoginToken
let ticket = try await postJSON("/nicezhuanye/ssoLogin/getTicket",
    body: ["UserID": teacherUserID, "token": "",      // 空 token
           "parameter": ["UserID": teacherUserID, "roleType": "teacher"]],
    ...)
```

### 加密（`Crypto.swift`）

```
base64( AES-128-ECB-PKCS7( gzip(JSON) ) )   密钥 = "RequestMappingHa"
```

### 查分（`API.swift`）

```
GET /api/exam/plan/class      → 班级列表
GET /api/exam/plan/student    → 学生名单（匹配姓名）
GET /api/analysis/data/monitor/exam/student/course  → 各科成绩+排名
```

---

## 五、注意事项

1. **AES-ECB** 用 CommonCrypto（`import CommonCrypto`），CryptoKit 不支持 ECB；
2. **gzip** 用 Compression framework（zlib）+ 手动 gzip 头尾 + CRC32 查表；
3. **token 有效期** 约 2 小时，`ScoreAPI` 已做惰性续期（`ensureToken`）；
4. 首次构建若 `CommonCrypto`/`Compression` 报找不到，确认 `import` 无误，CommonCrypto 在 Swift 中可直接 import；
5. 免签名模拟器运行：直接 Run 到模拟器即可，无需证书。

---

## 六、已知限制

- 学生作答答题卡扫描图：需学校扫描完成后才可获取（当前 `uploaderProgress=0`）；
- 试卷原卷（含题干）：系统内未上传 word/pdf，无法获取；
- 总分「年级排名」接口依赖成绩统计生成，当前未完成；班级排名可自行排序。
