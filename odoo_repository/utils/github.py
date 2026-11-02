# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import os
import time

import requests

GITHUB_URL = "https://github.com"
GITHUB_API_URL = "https://api.github.com"
# Timeout in seconds applied to every request to the GitHub API, to
# avoid jobs blocked forever on a hanging connection
REQUEST_TIMEOUT = 30


class GitHubRateLimitError(RuntimeError):
    """GitHub API rate limit reached.

    `retry_after` is the number of seconds to wait before retrying.
    """

    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


def _get_retry_after(response):
    """Return seconds to wait if `response` is a rate limit error, else None."""
    if response.status_code not in (403, 429):
        return None
    headers = response.headers
    if headers.get("Retry-After"):
        return int(headers["Retry-After"])
    if headers.get("X-RateLimit-Remaining") == "0":
        reset = int(headers.get("X-RateLimit-Reset", 0))
        return max(reset - int(time.time()), 60)
    if "rate limit" in response.text.lower():
        return 60
    return None


def _get_headers(env):
    """Return HTTP headers to request GitHub API."""
    headers = {"Accept": "application/vnd.github.groot-preview+json"}
    key = "odoo_repository_github_token"
    token = env["ir.config_parameter"].sudo().get_param(key, "") or os.environ.get(
        "GITHUB_TOKEN"
    )
    if token:
        headers.update({"Authorization": f"token {token}"})
    return headers


def _check_response(response):
    """Return the JSON payload of a GitHub API response.

    Raise on error, taking care of GitHub rate limits.
    """
    if not response.ok:
        retry_after = _get_retry_after(response)
        if retry_after:
            raise GitHubRateLimitError(response.text, retry_after)
        raise RuntimeError(response.text)
    return response.json()


def request(env, url, method="get", params=None, json=None, timeout=REQUEST_TIMEOUT):
    """Request GitHub API."""
    full_url = f"{GITHUB_API_URL}/{url}"
    kwargs = {"headers": _get_headers(env), "timeout": timeout}
    if json:
        kwargs.update(json=json)
    if params:
        kwargs.update(params=params)
    response = getattr(requests, method)(full_url, **kwargs)
    return _check_response(response)


def get_repo_info(env, org, name):
    """Return information about a GitHub repository, or None if not found.

    If the repository was renamed, GitHub redirects the query to the
    current repository: the returned payload describes it under its
    current name ('full_name').
    Return ``None`` if the repository does not exist (HTTP 404).
    Raise on any other error.
    """
    full_url = f"{GITHUB_API_URL}/repos/{org}/{name}"
    response = requests.get(
        full_url, headers=_get_headers(env), timeout=REQUEST_TIMEOUT
    )
    if response.status_code == 404:
        # Repository deleted from GitHub
        return None
    return _check_response(response)
