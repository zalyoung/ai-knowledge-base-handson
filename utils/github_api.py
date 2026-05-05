import json
import logging
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def get_repo_info(owner: str, repo: str) -> Optional[dict]:
    """Fetch basic repository information from GitHub API.

    Args:
        owner: Repository owner (username or organization).
        repo: Repository name.

    Returns:
        A dict containing stars, forks, and description if successful,
        or None if the request fails.

    Raises:
        ValueError: If owner or repo is empty.
    """
    if not owner or not repo:
        raise ValueError("owner and repo must be non-empty strings")

    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    req = Request(url, headers={"Accept": "application/vnd.github.v3+json"})

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "description": data.get("description", ""),
        }
    except (URLError, OSError):
        logger.exception("Failed to fetch repo info for %s/%s", owner, repo)
        return None
