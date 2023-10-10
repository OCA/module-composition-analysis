# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import os

import requests

GITHUB_URL = "https://github.com"
GITHUB_API_URL = "https://api.github.com"


def request(env, url, method="get", params=None, json=None):
    """Request GitHub API."""
    headers = {"Accept": "application/vnd.github.groot-preview+json"}
    key = "odoo_repository_github_token"
    token = (
        env["ir.config_parameter"].get_param(key, "")
        or os.environ.get("GITHUB_TOKEN")
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
        raise RuntimeError(response.text)
    return response.json()
