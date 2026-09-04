from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
CLOSING_ISSUE_RE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b")


class GitHubFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class PullRequestAddress:
    owner: str
    repository: str
    number: int


def parse_pull_request_url(url: str) -> PullRequestAddress:
    match = PR_URL_RE.fullmatch(url.strip())
    if not match:
        raise ValueError("Use a full GitHub PR URL such as https://github.com/owner/repo/pull/123")
    return PullRequestAddress(match.group(1), match.group(2), int(match.group(3)))


def fetch_pull_request(url: str, token: str | None = None) -> dict[str, object]:
    address = parse_pull_request_url(url)
    api_url = f"https://api.github.com/repos/{address.owner}/{address.repository}/pulls/{address.number}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Local-Blog-Manager"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(api_url, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubFetchError("GitHub API rate limit reached. Continue with manual entry or configure a token later.") from exc
        raise GitHubFetchError(f"GitHub returned HTTP {exc.code}. Continue with manual entry.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubFetchError("GitHub could not be reached. Continue with manual entry.") from exc

    body = str(payload.get("body") or "")
    issue_numbers = sorted({int(value) for value in CLOSING_ISSUE_RE.findall(body)})
    issue_number = issue_numbers[0] if len(issue_numbers) == 1 else None
    repository_url = f"https://github.com/{address.owner}/{address.repository}"
    return {
        "repository": repository_url,
        "owner": address.owner,
        "repositoryName": address.repository,
        "number": int(payload.get("number") or address.number),
        "title": str(payload.get("title") or ""),
        "url": str(payload.get("html_url") or url),
        "merged": bool(payload.get("merged_at")),
        "mergedAt": str(payload.get("merged_at") or ""),
        "author": str((payload.get("user") or {}).get("login") or ""),
        "issueNumber": issue_number,
        "issueUrl": f"{repository_url}/issues/{issue_number}" if issue_number else "",
    }
