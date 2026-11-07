import urllib.request, ssl, json, gzip, base64, sys, os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

KEY = b"RequestMappingHa"
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

TOKEN = "userToken-allparenta0a97755c1779e2e3525bd5407859b5d"
USERID = "1460593790569289728"
SYSTEMID = "700365677323"
BASE = "https://school.nicezhuanye.com"

def enc(s):
    gz = gzip.compress(s.encode("utf-8"))
    return base64.b64encode(AES.new(KEY, AES.MODE_ECB).encrypt(pad(gz, 16))).decode()

def dec(b64):
    b = base64.b64decode(b64)
    return gzip.decompress(unpad(AES.new(KEY, AES.MODE_ECB).decrypt(b), 16)).decode("utf-8")

def post(path, data, encrypt=True, host=None, extra_headers=None):
    url = (host or BASE) + path
    body = data if isinstance(data, str) else json.dumps(data)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "hqjl-user": USERID,
        "hqjl-token": TOKEN,
        "hqjlblkey": SYSTEMID,
    }
    if encrypt:
        body = enc(body)
        headers["X-HQJL-AJAX"] = "HQJL"
        headers["Content-Type"] = "application/json; charset=utf-8"
    else:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST", headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=40, context=ctx)
        raw = r.read()
        txt = raw.decode("utf-8", "replace")
        return r.status, txt, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, raw.decode("utf-8", "replace"), raw

def try_decrypt(txt):
    # if it looks like base64 and decrypts to JSON, return decrypted
    t = txt.strip()
    if not t:
        return txt
    try:
        d = dec(t)
        return d
    except Exception:
        return txt

if __name__ == "__main__":
    import json as _j
    ep = sys.argv[1] if len(sys.argv) > 1 else "/nicezhuanye/dashboard/Get/parentDashboardCards"
    body = _j.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    enc_flag = sys.argv[3].lower() != "plain" if len(sys.argv) > 3 else True
    st, txt, raw = post(ep, body, encrypt=enc_flag)
    print("STATUS", st, "RAW_LEN", len(raw))
    print("RAW head:", txt[:300])
    d = try_decrypt(txt)
    if d != txt:
        print("=== DECRYPTED ===")
        print(d)
