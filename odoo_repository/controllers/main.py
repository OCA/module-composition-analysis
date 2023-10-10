# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import json

from odoo import http


class OdooRepository(http.Controller):
    @http.route("/odoo-repository/data", type="http", auth="none", csrf=False)
    def index(self, orgs: str = None, repositories: str = None, branches: str = None):
        """Returns modules data as JSON.

        This endpoint is used by secondary nodes that want to sync the data
        collected by the main node.

        Parameters are strings that can be set with multiple values separated
        by commas, e.g. `branches="15.0,16.0"`.
        """
        if orgs:
            orgs = orgs.split(",")
        if repositories:
            repositories = repositories.split(",")
        if branches:
            branches = branches.split(",")
        data = (
            http.request.env["odoo.module.branch"]
            .sudo()
            ._get_modules_data(orgs=orgs, repositories=repositories, branches=branches)
        )
        headers = {"Content-Type": "application/json"}
        return http.request.make_response(json.dumps(data), headers)
