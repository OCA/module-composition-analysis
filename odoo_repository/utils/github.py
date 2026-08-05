# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import os
import time

import requests

GITHUB_URL = "https://github.com"
GITHUB_API_URL = "https://api.github.com"


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


def request(env, url, method="get", params=None, json=None):
    """Request GitHub API."""
    headers = {"Accept": "application/vnd.github.groot-preview+json"}
    key = "odoo_repository_github_token"
    token = env["ir.config_parameter"].sudo().get_param(key, "") or os.environ.get(
        "GITHUB_TOKEN"
    )
    if token:
        headers.update({"Authorization": f"token {token}"})
    full_url = "/".join([GITHUB_API_URL, url])
    kwargs = {"headers": headers}
    if json:
        kwargs.update(json=json)
    if params:
        kwargs.update(params=params)
    response = getattr(requests, method)(full_url, **kwargs)
    if not response.ok:
        retry_after = _get_retry_after(response)
        if retry_after:
            raise GitHubRateLimitError(response.text, retry_after)
        raise RuntimeError(response.text)
    return response.json()
