"""FlareSolverr integration for pre-solving Cloudflare challenges.

Usage:
    cookies = solve_cloudflare_challenge(url, timeout=60)
    # Returns dict of cookies or None if FlareSolverr unavailable/failed
    
Then inject into Selenium:
    for name, value in cookies.items():
        driver.add_cookie({'name': name, 'value': value, 'domain': domain})
"""

import json
import logging
import requests
from typing import Optional, Dict
from urllib.parse import urlparse
from pathlib import Path

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    """Client for FlareSolverr proxy service.
    
    FlareSolverr runs on localhost:8191 and solves Cloudflare challenges.
    See: https://github.com/FlareSolverr/FlareSolverr
    
    Install with Docker:
        docker run -p 8191:8191 flaresolverr/flaresolverr:latest
    """
    
    def __init__(self, endpoint: str = "http://localhost:8191/v1"):
        """Initialize FlareSolverr client.
        
        Args:
            endpoint: FlareSolverr API endpoint (default localhost:8191)
        """
        self.endpoint = endpoint
        self.timeout = 120  # FlareSolverr can be slow
        self._session_id = None
    
    def is_available(self) -> bool:
        """Check if FlareSolverr is running and responding."""
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
        """Solve Cloudflare challenge for a URL.
        
        Args:
            url: Target URL (should trigger Cloudflare challenge)
            session_id: Reuse existing session (keeps cookies)
            timeout: Max seconds to wait for challenge solution
            user_agent: Override User-Agent (optional)
        
        Returns:
            Dict of cookies {name: value} or None if failed
            
        Example:
            >>> client = FlareSolverrClient()
            >>> cookies = client.solve_challenge("https://example.com")
            >>> # Inject cookies into Selenium before navigating
        """
        if not self.is_available():
            logger.error("FlareSolverr not running at %s", self.endpoint)
            return None
        
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": timeout * 1000,  # Convert to milliseconds
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
                timeout=timeout + 10,  # Add buffer for network latency
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") != "ok":
                logger.error(
                    "FlareSolverr failed: %s",
                    result.get("message", "unknown error")
                )
                return None
            
            # Extract cookies from solution
            solution = result.get("solution", {})
            cookies_list = solution.get("cookies", [])
            
            if not cookies_list:
                logger.warning("FlareSolverr returned no cookies")
                return None
            
            # Store session ID for reuse on same domain
            if result.get("session"):
                self._session_id = result["session"]
                logger.debug("FlareSolverr session ID: %s", self._session_id)
            
            # Convert cookie list to dict
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
        """Get current session ID for reuse."""
        return self._session_id
    
    def clear_session(self):
        """Clear session ID to force new challenge solve."""
        self._session_id = None


class CookieCache:
    """Simple persistent cookie cache.
    
    Stores solved cookies on disk so you don't re-solve on every run.
    Useful for long-running bots or repeated executions.
    """
    
    def __init__(self, cache_dir: str = ".flaresolverr_cache"):
        """Initialize cookie cache.
        
        Args:
            cache_dir: Directory to store cached cookies
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_key(self, url: str) -> str:
        """Get cache filename from URL (sanitized domain)."""
        domain = urlparse(url).netloc
        # Sanitize domain for filename
        safe_domain = domain.replace(":", "_").replace("/", "_")
        return f"cookies_{safe_domain}.json"
    
    def get(self, url: str) -> Optional[Dict[str, str]]:
        """Get cached cookies for URL.
        
        Args:
            url: Target URL
        
        Returns:
            Dict of cookies or None if not cached
        """
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
        """Cache solved cookies for URL.
        
        Args:
            url: Target URL
            cookies: Cookie dict to cache
        """
        cache_file = self.cache_dir / self._get_cache_key(url)
        
        try:
            with open(cache_file, "w") as f:
                json.dump({"cookies": cookies, "url": url}, f, indent=2)
            
            logger.info("Cached cookies to %s", cache_file.name)
        
        except IOError as e:
            logger.warning("Could not write cookie cache: %s", e)
    
    def clear(self, url: str = None):
        """Clear cached cookies.
        
        Args:
            url: Clear only this URL (or clear all if None)
        """
        if url:
            cache_file = self.cache_dir / self._get_cache_key(url)
            cache_file.unlink(missing_ok=True)
            logger.info("Cleared cookies for %s", url)
        else:
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            logger.info("Cleared all cached cookies")


def inject_cookies_into_driver(driver, cookies: Dict[str, str], domain: str):
    """Inject solved cookies into Selenium WebDriver.
    
    Args:
        driver: Selenium WebDriver instance
        cookies: Dict of {name: value}
        domain: Domain to set cookies for (e.g., "example.com")
    
    Example:
        cookies = {"cf_clearance": "xyz123..."}
        inject_cookies_into_driver(driver, cookies, "example.com")
    """
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


# Global instances (reuse across multiple runs)
_flaresolverr_client = None
_cookie_cache = None


def get_flaresolverr_client(endpoint: str = "http://localhost:8191/v1") -> FlareSolverrClient:
    """Get or create global FlareSolverr client."""
    global _flaresolverr_client
    if _flaresolverr_client is None:
        _flaresolverr_client = FlareSolverrClient(endpoint)
    return _flaresolverr_client


def get_cookie_cache(cache_dir: str = ".flaresolverr_cache") -> CookieCache:
    """Get or create global cookie cache."""
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
    """Solve Cloudflare challenge for a URL (high-level API).
    
    Args:
        url: Target URL
        use_cache: Try cache first, then FlareSolverr, then cache result
        user_agent: Override User-Agent
        timeout: Max seconds to wait
    
    Returns:
        Dict of solved cookies or None if failed
    
    Example:
        >>> cookies = solve_cloudflare_challenge("https://example.com")
        >>> if cookies:
        ...     inject_cookies_into_driver(driver, cookies, "example.com")
    """
    client = get_flaresolverr_client()
    cache = get_cookie_cache() if use_cache else None
    
    # Step 1: Try cache
    if cache:
        cached = cache.get(url)
        if cached:
            logger.info("Using cached cookies for %s", url)
            return cached
    
    # Step 2: Check FlareSolverr availability
    if not client.is_available():
        logger.error("FlareSolverr not running and no cached cookies available")
        return None
    
    # Step 3: Solve challenge
    cookies = client.solve_challenge(url, user_agent=user_agent, timeout=timeout)
    
    # Step 4: Cache result
    if cookies and cache:
        cache.set(url, cookies)
    
    return cookies
