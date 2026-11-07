import urllib.request, ssl, json, re

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
NZY = "https://school.nicezhuanye.com"
DN = "https://nicezhuanye.dongni100.com"
NZY_TOKEN = "userToken-allparenta0a97755c1779e2e3525bd5407859b5d"
NZY_USERID = "1460593790569289728"
RELATIVE_ID = 799219206

def raw_req(base, method, path, data=None, headers=None):
    h = {"User-Agent":"Mozilla/5.0","X-Requested-With":"XMLHttpRequest"}
    if headers: h.update(headers)
    body = json.dumps(data).encode() if data is not None else None
    if data is not None: h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(base + path, data=body, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=40)
        return resp.status, resp.read().decode("utf-8","replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8","replace"), e.headers

def get_dongni_token():
    st, txt, hd = raw_req(NZY, "POST", "/nicezhuanye/ssoLogin/getTicket",
        {"UserID":NZY_USERID,"token":NZY_TOKEN,"parameter":{"UserID":NZY_USERID,"roleType":"parent"}},
        {"hqjl-token":NZY_TOKEN,"hqjl-user":NZY_USERID})
    ticket = json.loads(txt)["result"]
    st, txt, hd = raw_req(DN, "POST", "/api/base/data/system/auth/sso",
        {"dictKey":"nicezhuanye","nicezhuanye":"prod","ticket":ticket,"clientType":1})
    dlt = json.loads(txt)["data"]["dongniLoginToken"]
    st, txt, hd = raw_req(DN, "POST", "/api/base/data/auth/token", {}, {"DONGNI-LOGIN":dlt})
    sc = hd.get_all("Set-Cookie") if hasattr(hd,'get_all') else [hd.get("Set-Cookie") or ""]
    m = re.search(r'dongniLoginToken=([^;]+)', " ".join(sc))
    return m.group(1) if m else dlt

def dn(method, path, data=None, params=None):
    dlt = get_dongni_token()
    qs = "?" + urllib.parse.urlencode(params) if params else ""
    return raw_req(DN, method, path + qs, data=data, headers={"DONGNI-LOGIN":dlt, "Cookie":"dongniLoginToken="+dlt})

if __name__ == "__main__":
    import urllib.parse
    dlt = get_dongni_token()
    print("token ok:", dlt[:20])
