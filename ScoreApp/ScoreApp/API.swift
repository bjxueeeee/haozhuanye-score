//
//  API.swift
//  ScoreApp
//
//  网络层：越权拿教师 token + 查分 + 判卷进度
//

import Foundation

// MARK: - 数据模型

struct StudentScore: Identifiable {
    let id = UUID()
    let course: String
    let score: Double
    let full: Double
    let examRank: Int
    let classRank: Int
    let avg: Double

    var rate: Double { full > 0 ? score / full * 100 : 0 }
}

struct QueryResult {
    var name: String = ""
    var grade: String = ""
    var className: String = ""
    var studentNum: String = ""
    let total: Double
    let totalFull: Double
    let classRank: Int?
    let classCount: Int?
    let courses: [StudentScore]

    var rate: Double { totalFull > 0 ? total / totalFull * 100 : 0 }
}

struct SubjectProgress: Identifiable {
    let id = UUID()
    let name: String
    let full: Double
    let avg: Double
    let rate: Int
    let answerStatus: Int?
    let entrust: Int?
}

struct GradeProgress: Identifiable {
    let id = UUID()
    let grade: String
    let overall: Int
    let totalFull: Double
    let subjects: [SubjectProgress]
}

// MARK: - 考试配置（两个校区 × 三个年级）

struct ExamConfig {
    let school: String
    let grade: String
    let schoolId: Int
    let examId: Int
}

let EXAM_CONFIGS: [ExamConfig] = [
    ExamConfig(school: "本部", grade: "初一", schoolId: 5261712, examId: 1079615161),
    ExamConfig(school: "本部", grade: "初二", schoolId: 5261712, examId: 5872340),
    ExamConfig(school: "本部", grade: "初三", schoolId: 5261712, examId: 945420786),
    ExamConfig(school: "来广营", grade: "初一", schoolId: 5261711, examId: 1750726433),
    ExamConfig(school: "来广营", grade: "初二", schoolId: 5261711, examId: 1213832294),
    ExamConfig(school: "来广营", grade: "初三", schoolId: 5261711, examId: 1482267763),
]

// MARK: - 网络层

actor ScoreAPI {
    static let shared = ScoreAPI()

    private let nzyBase = "https://school.nicezhuanye.com"
    private let dnBase  = "https://nicezhuanye.dongni100.com"
    /// 家长 token（用于越权）
    private let parentToken = "userToken-allparenta0a97755c1779e2e3525bd5407859b5d"
    /// 查分老师（李冬）
    private let teacherUserID = "1445657423926137926"

    private var dongniToken: String?
    private var session = URLSession.shared

    // MARK: - 越权：getTicket（不校验 token）→ SSO 拿教师 dongniLoginToken

    func acquireTeacherToken() async throws -> String {
        // 1. getTicket：空 token + 教师 userID + roleType=teacher
        let ticketResp: [String: Any] = try await postJSON(
            nzyBase + "/nicezhuanye/ssoLogin/getTicket",
            body: ["UserID": teacherUserID, "token": "",
                   "parameter": ["UserID": teacherUserID, "roleType": "teacher"]],
            headers: ["hqjl-user": teacherUserID, "hqjl-token": ""],
            encrypt: false
        )
        guard let ticket = ticketResp["result"] as? String else {
            throw NSError(domain: "API", code: 1, userInfo: [NSLocalizedDescriptionKey: "getTicket 失败"])
        }

        // 2. SSO → dongniLoginToken
        let ssoResp: [String: Any] = try await postJSON(
            dnBase + "/api/base/data/system/auth/sso",
            body: ["dictKey": "nicezhuanye", "nicezhuanye": "prod", "ticket": ticket, "clientType": 1],
            headers: nil,
            encrypt: false
        )
        guard let data = ssoResp["data"] as? [String: Any],
              let token = data["dongniLoginToken"] as? String else {
            throw NSError(domain: "API", code: 2, userInfo: [NSLocalizedDescriptionKey: "SSO 失败"])
        }
        dongniToken = token
        return token
    }

    // MARK: - 查分

    func query(name: String) async throws -> [QueryResult] {
        let token = try await ensureToken()
        // 1. 遍历所有考试，找学生（name 匹配）
        for cfg in EXAM_CONFIGS {
            // 2. 查班级
            let classResp: [String: Any] = try await getJSON(
                dnBase + "/api/exam/plan/class",
                params: ["examId": cfg.examId, "schoolId": cfg.schoolId],
                token: token
            )
            guard let classes = classResp["data"] as? [[String: Any]] else { continue }

            for cls in classes {
                guard let classId = cls["classId"] as? Int,
                      let className = cls["className"] as? String else { continue }
                let stuResp: [String: Any] = try await getJSON(
                    dnBase + "/api/exam/plan/student",
                    params: ["examId": cfg.examId, "schoolId": cfg.schoolId, "classId": classId],
                    token: token
                )
                guard let students = stuResp["data"] as? [String: Any],
                      let list = students["student"] as? [[String: Any]] else { continue }

                for s in list where (s["studentName"] as? String) == name {
                    let score = try await fetchScore(studentId: s["studentId"] as? Int ?? 0,
                                                     examId: cfg.examId,
                                                     schoolId: cfg.schoolId,
                                                     token: token)
                    if var score = score {
                        score.name = name
                        score.grade = cfg.grade
                        score.className = className
                        score.studentNum = (s["studentNum"] as? String) ?? ""
                        return [score]
                    }
                }
            }
        }
        throw NSError(domain: "API", code: 3, userInfo: [NSLocalizedDescriptionKey: "未找到学生「\(name)」"])
    }

    private func fetchScore(studentId: Int, examId: Int, schoolId: Int, token: String) async throws -> QueryResult? {
        // 1. 满分表
        let paperResp: [String: Any] = try await getJSON(
            dnBase + "/api/exam/plan/paper",
            params: ["examId": examId, "schoolId": schoolId],
            token: token
        )
        var fullMap: [String: Double] = [:]
        if let papers = paperResp["data"] as? [[String: Any]] {
            for p in papers {
                if let cn = p["courseName"] as? String, let fm = p["fullMark"] as? Double {
                    fullMap[cn] = fm
                }
            }
        }

        // 2. 学生成绩
        let scoreResp: [String: Any] = try await getJSON(
            dnBase + "/api/analysis/data/monitor/exam/student/course",
            params: ["examId": examId, "studentId": studentId, "schoolId": schoolId],
            token: token
        )
        guard let data = scoreResp["data"] as? [String: Any],
              let courses = data["courses"] as? [[String: Any]] else { return nil }

        var list: [StudentScore] = []
        var total = 0.0
        for c in courses {
            let cn = c["courseName"] as? String ?? ""
            let score = (c["totalScore"] as? Double) ?? 0
            let full = fullMap[cn] ?? 0
            total += score
            list.append(StudentScore(
                course: cn,
                score: score,
                full: full,
                examRank: (c["examRanking"] as? Int) ?? 0,
                classRank: (c["classRanking"] as? Int) ?? 0,
                avg: Double(c["averageScore"] as? String ?? "0") ?? 0
            ))
        }
        let totalFull = fullMap.values.reduce(0, +)
        return QueryResult(name: "", grade: "", className: "", studentNum: "",
                           total: total, totalFull: totalFull,
                           classRank: nil, classCount: nil, courses: list)
    }

    // MARK: - 判卷进度

    func progress() async throws -> [GradeProgress] {
        let token = try await ensureToken()
        var groups: [GradeProgress] = []
        for cfg in EXAM_CONFIGS {
            let markResp: [String: Any] = try await getJSON(
                dnBase + "/api/exam/mark/progress/course/case",
                params: ["examId": cfg.examId, "schoolId": cfg.schoolId],
                token: token
            )
            var meta: [String: (Int?, Int?)] = [:]
            if let arr = markResp["data"] as? [[String: Any]] {
                for c in arr {
                    meta[c["courseName"] as? String ?? ""] = (c["answerStatus"] as? Int, c["paperEntrustStatus"] as? Int)
                }
            }
            // 满分
            let paperResp: [String: Any] = try await getJSON(
                dnBase + "/api/exam/plan/paper",
                params: ["examId": cfg.examId, "schoolId": cfg.schoolId],
                token: token
            )
            var fullMap: [String: Double] = [:]
            if let papers = paperResp["data"] as? [[String: Any]] {
                for p in papers {
                    if let cn = p["courseName"] as? String, let fm = p["fullMark"] as? Double {
                        fullMap[cn] = fm
                    }
                }
            }
            // 班均：用第一个学生（简化为空，仅展示满分与状态）
            var subjects: [SubjectProgress] = []
            for (cn, full) in fullMap {
                let m = meta[cn]
                subjects.append(SubjectProgress(name: cn, full: full, avg: 0,
                                                rate: 0, answerStatus: m?.0, entrust: m?.1))
            }
            groups.append(GradeProgress(grade: "\(cfg.school)·\(cfg.grade)", overall: 0,
                                        totalFull: fullMap.values.reduce(0, +), subjects: subjects))
        }
        return groups
    }

    // MARK: - HTTP 辅助

    private func ensureToken() async throws -> String {
        if let t = dongniToken { return t }
        return try await acquireTeacherToken()
    }

    private func getJSON(_ url: String, params: [String: Any], token: String) async throws -> [String: Any] {
        var comps = URLComponents(string: url)!
        comps.queryItems = params.map { URLQueryItem(name: $0.key, value: "\($0.value)") }
        var req = URLRequest(url: comps.url!)
        req.httpMethod = "GET"
        req.setValue(token, forHTTPHeaderField: "DONGNI-LOGIN")
        req.setValue("dongniLoginToken=\(token)", forHTTPHeaderField: "Cookie")
        req.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")
        let (data, _) = try await session.data(for: req)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    private func postJSON(_ url: String, body: [String: Any], headers: [String: String]?, encrypt: Bool) async throws -> [String: Any] {
        var req = URLRequest(url: URL(string: url)!)
        req.httpMethod = "POST"
        req.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        req.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")
        req.setValue("XMLHttpRequest", forHTTPHeaderField: "X-Requested-With")
        if let headers {
            for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        }

        if encrypt {
            guard let enc = HQJLCrypto.encryptJSON(body) else {
                throw NSError(domain: "Crypto", code: 4)
            }
            req.setValue("HQJL", forHTTPHeaderField: "X-HQJL-AJAX")
            req.httpBody = enc.data(using: .utf8)
        } else {
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (data, _) = try await session.data(for: req)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }
}
