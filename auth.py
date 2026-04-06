"""CAS 统一身份认证登录 + token 管理"""

import re
import time
import base64
import logging
from urllib.parse import urlencode, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


class TokenManager:
    """管理 access_token 的获取和缓存"""

    def __init__(self, config: dict):
        self.config = config
        self._token = None
        self._token_time = 0
        self._expires_in = 6047999
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 "
                          "Mobile Safari/537.36"
        })

    @property
    def token(self) -> str:
        if self._token and (time.time() - self._token_time) < self._expires_in - 3600:
            return self._token
        # 登录失败时最多重试3次，每次间隔5秒
        last_err = None
        for attempt in range(3):
            try:
                self._login()
                return self._token
            except Exception as e:
                last_err = e
                logger.warning("登录失败（第%d次）: %s，5秒后重试...", attempt + 1, e)
                time.sleep(5)
        raise AuthError(f"登录重试3次均失败: {last_err}")

    def _login(self):
        """完整的 CAS 登录流程"""
        logger.info("开始 CAS 登录...")
        cas_url = self.config["auth"]["cas_url"]
        service_url = self.config["auth"]["service_url"]
        username = self.config["auth"]["username"]
        password = self.config["auth"]["password"]
        base_url = self.config["api"]["base_url"]

        # 步骤1: 获取 CAS 登录页面
        login_url = f"{cas_url}/login?service={requests.utils.quote(service_url, safe='')}"
        resp = self.session.get(login_url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        # 取 userNameLogin 表单里的字段
        form = soup.find("input", {"name": "cllt", "value": "userNameLogin"})
        form = form.find_parent("form") if form else None
        if form:
            execution = form.find("input", {"name": "execution"})
            execution = execution.get("value", "") if execution else ""
            salt_tag = form.find("input", {"id": "pwdEncryptSalt"})
            salt = salt_tag.get("value", "") if salt_tag else ""
        else:
            execution = self._extract_field(soup, "execution")
            salt_tag = soup.find("input", {"id": "pwdEncryptSalt"})
            salt = salt_tag.get("value", "") if salt_tag else self._extract_salt(resp.text)

        if not execution:
            raise AuthError("无法从 CAS 页面获取 execution 字段")
        if not salt:
            raise AuthError("无法从 CAS 页面获取 pwdEncryptSalt")

        # 步骤2: 加密密码并提交登录
        encrypted_pwd = self._encrypt_password(password, salt)
        post_data = {
            "username": username,
            "password": encrypted_pwd,
            "captcha": "",
            "rememberMe": "true",
            "_eventId": "submit",
            "lt": "",
            "cllt": "userNameLogin",
            "dllt": "generalLogin",
            "execution": execution,
        }

        # 不自动跟随重定向，手动处理
        resp = self.session.post(login_url, data=post_data, allow_redirects=False)

        if resp.status_code != 302:
            raise AuthError(f"CAS 登录失败，状态码: {resp.status_code}")

        # 步骤3: 跟随重定向链，获取最终的 ticket 凭证
        ticket = self._follow_redirects(resp)
        if not ticket:
            raise AuthError("无法从重定向链中获取 ticket 凭证")

        logger.info("CAS 登录成功，获取到 ticket 凭证")

        # 步骤4: 用 ticket 换取 access_token
        token_data = {
            "username": ticket,
            "password": ticket,
            "grant_type": "password",
            "scope": "all",
            "loginFrom": "h5",
            "logintype": "sso",
            "device_token": "h5",
            "synAccessSource": "h5",
        }

        resp = self.session.post(
            f"{base_url}/berserker-auth/oauth/token",
            data=token_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic bW9iaWxlX3NlcnZpY2VfcGxhdGZvcm06bW9iaWxlX3NlcnZpY2VfcGxhdGZvcm1fc2VjcmV0",
            },
        )
        resp.raise_for_status()
        result = resp.json()

        if "access_token" not in result:
            raise AuthError(f"获取 token 失败: {result}")

        self._token = result["access_token"]
        self._token_time = time.time()
        self._expires_in = result.get("expires_in", 6047999)
        logger.info("access_token 获取成功，有效期 %d 秒", self._expires_in)

    def _follow_redirects(self, resp) -> str:
        """手动跟随重定向链直到 200，提取最终的加密 ticket 凭证"""
        ticket = None
        for _ in range(20):
            location = resp.headers.get("Location")
            if not location:
                break

            # 记录非 ST- 的 ticket
            if "ticket=" in location:
                t = parse_qs(urlparse(location).query).get("ticket", [""])[0]
                t = unquote(t)
                if t and not t.startswith("ST-"):
                    ticket = t

            resp = self.session.get(location, allow_redirects=False)

            if resp.status_code == 200:
                # 从最终 URL 再提取一次
                t = parse_qs(urlparse(resp.url).query).get("ticket", [""])[0]
                t = unquote(t)
                if t and not t.startswith("ST-"):
                    ticket = t
                return ticket

        return ticket

    @staticmethod
    def _extract_ticket(url: str) -> str:
        """从 URL 中提取 ticket 参数的原始（单次解码）值"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get("ticket", [None])[0]

    @staticmethod
    def _encrypt_password(password: str, salt: str) -> str:
        """标准金智 CAS AES-CBC 加密: getAesString(randomString(64)+pwd, salt, randomString(16))"""
        import random
        aes_chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
        def random_str(n):
            return "".join(random.choice(aes_chars) for _ in range(n))

        key = salt.strip().encode("utf-8")
        iv = random_str(16).encode("utf-8")
        plain = (random_str(64) + password).encode("utf-8")
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(pad(plain, AES.block_size))
        return base64.b64encode(encrypted).decode("utf-8")

    @staticmethod
    def _extract_field(soup: BeautifulSoup, name: str) -> str:
        tag = soup.find("input", {"name": name})
        if tag:
            return tag.get("value", "")
        return ""

    @staticmethod
    def _extract_salt(html: str) -> str:
        """从页面中提取 pwdEncryptSalt"""
        m = re.search(r'pwdEncryptSalt\s*=\s*"([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'pwdDefaultEncryptSalt\s*=\s*"([^"]+)"', html)
        if m:
            return m.group(1)
        return ""


if __name__ == "__main__":
    import yaml
    logging.basicConfig(level=logging.INFO)
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tm = TokenManager(cfg)
    print("Token:", tm.token[:50] + "...")
