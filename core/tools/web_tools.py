"""
Web tools — fetch pages and make HTTP API requests.
"""
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseTool, ToolResult

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MultiAgentSystem/1.0)"}


class FetchWebPageTool(BaseTool):
    name = "fetch_webpage"
    description = (
        "Fetch a web page and extract its readable text content. "
        "Useful for reading documentation, articles, or any public URL."
    )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch"},
                "extract_text": {
                    "type": "boolean",
                    "description": "Strip HTML and return clean text only",
                    "default": True,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 8000,
                },
            },
            "required": ["url"],
        }

    async def execute(
        self, url: str, extract_text: bool = True, max_chars: int = 8000
    ) -> ToolResult:
        try:
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True, headers=_HEADERS
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                if extract_text:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "aside"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n", strip=True)
                    text = "\n".join(line for line in text.splitlines() if line.strip())
                    return ToolResult(success=True, output=text[:max_chars])
                return ToolResult(success=True, output=response.text[:max_chars])
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class HTTPRequestTool(BaseTool):
    name = "http_request"
    description = "Make an HTTP request (GET/POST/PUT/DELETE) to any REST API endpoint."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "default": "GET",
                },
                "headers": {"type": "object", "description": "Request headers"},
                "body": {"type": "object", "description": "JSON body for POST/PUT"},
                "params": {"type": "object", "description": "URL query parameters"},
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers or {},
                    json=body,
                    params=params,
                )
                try:
                    data = response.json()
                except Exception:
                    data = response.text
                return ToolResult(
                    success=True,
                    output={"status": response.status_code, "data": data},
                )
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))
