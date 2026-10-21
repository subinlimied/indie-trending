"""표준 라이브러리만 쓰는 작은 HTTP 도우미. 재시도와 429 대기를 담당합니다."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _ssl_context():
    """python.org 배포판 macOS 파이썬은 루트 인증서가 비어 있어 certifi 나 시스템 번들을 찾아 씁니다."""
    import os
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(p):
            return ssl.create_default_context(cafile=p)
    return ssl.create_default_context()


_CTX = _ssl_context()


def get(url, params=None, headers=None, retries=5, timeout=25, backoff=2.0):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            try:
                e.close()  # 응답 소켓을 닫지 않으면 CLOSE_WAIT 가 쌓입니다
            except Exception:  # noqa: BLE001
                pass
            if e.code == 429 or e.code >= 500:
                # 429 는 10, 20, 30... 초로 길게 쉽니다. Steam 리뷰 API 가 자주 겁니다.
                time.sleep(backoff * (attempt + 1) * (5 if e.code == 429 else 1))
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"GET failed after retries: {url} ({last})")


def get_json(url, params=None, **kw):
    body = get(url, params, **kw)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None
