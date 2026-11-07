#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量导出 6 个年级全部学生的详细成绩（各科分数/排名/总分）"""
import json, urllib.request, urllib.parse, ssl, sys, os
import concurrent.futures

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".pylibs"))

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
NZY = "https://school.nicezhuanye.com"; DN = "https://nicezhuanye.dongni100.com"
TCH_UID = "1445657423926137926"

def post(url, data, headers=None):
    h = {"User-Agent":"Mozilla/5.0","X-Requested-With":"XMLHttpRequest","Content-Type":"application/json; charset=utf-8"}
    if headers: h.update(headers)
    r = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST", headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=40, context=ctx)
        return resp.status, resp.read().decode("utf-8","replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace"), e.headers

st,t,h = post(NZY+"/nicezhuanye/ssoLogin/getTicket", {"UserID":TCH_UID,"token":"","parameter":{"UserID":TCH_UID,"roleType":"teacher"}}, {"hqjl-user":TCH_UID,"hqjl-token":""})
ticket = json.loads(t)["result"]
st,t,h = post(DN+"/api/base/data/system/auth/sso", {"dictKey":"nicezhuanye","nicezhuanye":"prod","ticket":ticket,"clientType":1})
dlt = json.loads(t)["data"]["dongniLoginToken"]
print("token ok")

def dn_get(path, params=None):
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    h = {"User-Agent":"Mozilla/5.0","DONGNI-LOGIN":dlt,"Cookie":"dongniLoginToken="+dlt}
    r = urllib.request.Request(DN + path + qs, method="GET", headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=40, context=ctx)
        return resp.status, resp.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")

# 6 个年级：校区/年级/schoolId/examId
GRADES = [
    ("本部","初一",5261712,1079615161),
    ("本部","初二",5261712,5872340),
    ("本部","初三",5261712,945420786),
    ("来广营","初一",5261711,1750726433),
    ("来广营","初二",5261711,1213832294),
    ("来广营","初三",5261711,1482267763),
]

# 满分表
paper_map = {}
for school, grade, sid, examId in GRADES:
    st, txt = dn_get("/api/exam/plan/paper", {"examId": examId, "schoolId": sid})
    try:
        paper_map[examId] = {p["courseName"]: p["fullMark"] for p in json.loads(txt).get("data", [])}
    except:
        paper_map[examId] = {}

# 扁平学生列表 + studentId
students = []
for school, grade, sid, examId in GRADES:
    st, txt = dn_get("/api/exam/plan/class", {"examId": examId, "schoolId": sid})
    try:
        classes = json.loads(txt).get("data", [])
    except:
        classes = []
    for c in classes:
        st, txt = dn_get("/api/exam/plan/student", {"examId": examId, "schoolId": sid, "classId": c["classId"]})
        try:
            sl = json.loads(txt).get("data", {}).get("student", [])
        except:
            sl = []
        for s in sl:
            students.append({
                "school": school, "grade": grade, "class": c["className"],
                "num": s.get("studentNum",""), "name": s.get("studentName",""),
                "studentId": s["studentId"], "examId": examId, "schoolId": sid,
            })
print("学生总数:", len(students))

def fetch_one(stu):
    st, txt = dn_get("/api/analysis/data/monitor/exam/student/course",
                     {"examId": stu["examId"], "studentId": stu["studentId"], "schoolId": stu["schoolId"]})
    try:
        courses = json.loads(txt).get("data", {}).get("courses", [])
    except:
        courses = []
    fm = paper_map.get(stu["examId"], {})
    total = 0.0
    cs = []
    for c in courses:
        name = c.get("courseName")
        score = c.get("totalScore", 0) or 0
        full = fm.get(name)
        total += score
        cs.append({
            "course": name, "score": score, "full": full,
            "examRank": c.get("examRanking"), "classRank": c.get("classRanking"),
            "avg": c.get("averageScore"),
        })
    total_full = sum(fm.values())
    return {
        "school": stu["school"], "grade": stu["grade"], "class": stu["class"],
        "num": stu["num"], "name": stu["name"],
        "total": round(total, 1), "totalFull": total_full,
        "courses": cs,
    }

results = []
done = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
    futs = {ex.submit(fetch_one, s): s for s in students}
    for fut in concurrent.futures.as_completed(futs):
        try:
            results.append(fut.result())
        except Exception as e:
            pass
        done += 1
        if done % 500 == 0:
            print(f"进度 {done}/{len(students)}")

out_path = os.path.join(BASE, "学生详细成绩_六校区.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False)
print(f"[OK] 导出完成: {out_path}")
print(f"共 {len(results)} 名学生详细成绩")
