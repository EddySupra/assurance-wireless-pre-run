import json
import logging
import requests
from typing import Optional, Dict
from urllib.parse import urlparse
from pathlib import Path

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    def __init__(self, endpoint: str = "http://localhost:8191/v1"):
        self.endpoint = endpoint
        self.timeout = 120
        self._session_id = None
    
    def is_available(self) -> bool:
        try:
            response = requests.get(
                self.endpoint.replace("/v1", ""),
                timeout=5
            )
            return response.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            logger.warning("FlareSolverr not available at %s", self.endpoint)
            return False
    
    def solve_challenge(
        self,
        url: str,
        session_id: Optional[str] = None,
        timeout: int = 120,
        user_agent: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        if not self.is_available():
            logger.error("FlareSolverr not running at %s", self.endpoint)
            return None
        
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": timeout * 1000,
        }
        
        if user_agent:
            payload["userAgent"] = user_agent
        
        if session_id:
            payload["session"] = session_id
            logger.debug("Reusing FlareSolverr session %s", session_id)
        else:
            logger.info("Starting new FlareSolverr session for %s", url)
        
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=timeout + 10,
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") != "ok":
                logger.error(
                    "FlareSolverr failed: %s",
                    result.get("message", "unknown error")
                )
                return None
            
            solution = result.get("solution", {})
            cookies_list = solution.get("cookies", [])
            
            if not cookies_list:
                logger.warning("FlareSolverr returned no cookies")
                return None
            
            if result.get("session"):
                self._session_id = result["session"]
                logger.debug("FlareSolverr session ID: %s", self._session_id)
            
            cookies = {}
            for cookie in cookies_list:
                name = cookie.get("name")
                value = cookie.get("value")
                if name and value:
                    cookies[name] = value
            
            logger.info("FlareSolverr solved challenge: %d cookies", len(cookies))
            return cookies
        
        except requests.Timeout:
            logger.error("FlareSolverr timeout (took >%ds)", timeout)
            return None
        except requests.RequestException as e:
            logger.error("FlareSolverr request failed: %s", e)
            return None
        except json.JSONDecodeError as e:
            logger.error("FlareSolverr returned invalid JSON: %s", e)
            return None
    
    def get_session_id(self) -> Optional[str]:
        return self._session_id
    
    def clear_session(self):
        self._session_id = None


class CookieCache:
    def __init__(self, cache_dir: str = ".flaresolverr_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_key(self, url: str) -> str:
        domain = urlparse(url).netloc
        safe_domain = domain.replace(":", "_").replace("/", "_")
        return f"cookies_{safe_domain}.json"
    
    def get(self, url: str) -> Optional[Dict[str, str]]:
        cache_file = self.cache_dir / self._get_cache_key(url)
        
        if not cache_file.exists():
            logger.debug("No cached cookies for %s", url)
            return None
        
        try:
            with open(cache_file) as f:
                data = json.load(f)
            
            logger.info("Loaded cached cookies from %s", cache_file.name)
            return data.get("cookies", {})
        
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Could not read cookie cache: %s", e)
            return None
    
    def set(self, url: str, cookies: Dict[str, str]):
        cache_file = self.cache_dir / self._get_cache_key(url)
        
        try:
            with open(cache_file, "w") as f:
                json.dump({"cookies": cookies, "url": url}, f, indent=2)
            
            logger.info("Cached cookies to %s", cache_file.name)
        
        except IOError as e:
            logger.warning("Could not write cookie cache: %s", e)
    
    def clear(self, url: str = None):
        if url:
            cache_file = self.cache_dir / self._get_cache_key(url)
            cache_file.unlink(missing_ok=True)
            logger.info("Cleared cookies for %s", url)
        else:
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            logger.info("Cleared all cached cookies")


def inject_cookies_into_driver(driver, cookies: Dict[str, str], domain: str):
    for name, value in cookies.items():
        try:
            driver.add_cookie({
                "name": name,
                "value": value,
                "domain": domain,
                "httpOnly": False,
                "secure": True,
                "sameSite": "None",
            })
            logger.debug("Injected cookie: %s", name)
        except Exception as e:
            logger.warning("Failed to inject cookie %s: %s", name, e)


_flaresolverr_client = None
_cookie_cache = None


def get_flaresolverr_client(endpoint: str = "http://localhost:8191/v1") -> FlareSolverrClient:
    global _flaresolverr_client
    if _flaresolverr_client is None:
        _flaresolverr_client = FlareSolverrClient(endpoint)
    return _flaresolverr_client


def get_cookie_cache(cache_dir: str = ".flaresolverr_cache") -> CookieCache:
    global _cookie_cache
    if _cookie_cache is None:
        _cookie_cache = CookieCache(cache_dir)
    return _cookie_cache


def solve_cloudflare_challenge(
    url: str,
    use_cache: bool = True,
    user_agent: Optional[str] = None,
    timeout: int = 120,
) -> Optional[Dict[str, str]]:
    client = get_flaresolverr_client()
    cache = get_cookie_cache() if use_cache else None
    
    if cache:
        cached = cache.get(url)
        if cached:
            logger.info("Using cached cookies for %s", url)
            return cached
    
    if not client.is_available():
        logger.error("FlareSolverr not running and no cached cookies available")
        return None
    
    cookies = client.solve_challenge(url, user_agent=user_agent, timeout=timeout)
    
    if cookies and cache:
        cache.set(url, cookies)
    
    return cookies
