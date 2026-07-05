from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpClientError(RuntimeError):
    pass


def safe_url(url: str) -> str:
    return re.sub(r"/bot[^/]+/", "/bot<hidden>/", url)


@dataclass(frozen=True)
class JsonHttpClient:
    timeout_seconds: float = 15.0
    user_agent: str = "crypto-signal-agent/0.1"

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        full_url = url
        if params:
            full_url = f"{url}?{urlencode(params)}"
        request = Request(full_url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            return self._curl_json("GET", full_url)
        except URLError as exc:
            return self._curl_json("GET", full_url)
        except TimeoutError as exc:
            return self._curl_json("GET", full_url)
        return json.loads(payload)

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            return self._curl_json("POST", url, payload)
        except URLError as exc:
            return self._curl_json("POST", url, payload)
        except TimeoutError as exc:
            return self._curl_json("POST", url, payload)
        return json.loads(body)

    def _curl_json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        command = [
            "curl",
            "-sS",
            "-f",
            "--max-time",
            str(int(self.timeout_seconds)),
            "-H",
            f"User-Agent: {self.user_agent}",
        ]
        if method == "POST":
            command.extend(
                [
                    "-X",
                    "POST",
                    "-H",
                    "Content-Type: application/json",
                    "--data",
                    json.dumps(payload or {}),
                ]
            )
        command.append(url)
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            message = result.stderr.strip() or f"curl exit {result.returncode}"
            raise HttpClientError(f"сетевая ошибка для {safe_url(url)}: {safe_url(message)}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise HttpClientError(f"некорректный JSON от {safe_url(url)}") from exc
