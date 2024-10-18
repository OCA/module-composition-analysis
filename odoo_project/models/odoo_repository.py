# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooRepository(models.Model):
    _inherit = "odoo.repository"

    project_ids = fields.One2many(
        comodel_name="odoo.project",
        inverse_name="repository_id",
        string="Projects",
    )
    project_count = fields.Integer(compute="_compute_project_count")

    @api.depends("project_ids")
    def _compute_project_count(self):
        for rec in self:
            rec.project_count = len(rec.project_ids)

    def action_view_projects(self):
        self.ensure_one()
        projects = self.project_ids
        action = self.env["ir.actions.actions"]._for_xml_id(
            "odoo_project.odoo_project_action"
        )
        if len(projects) > 1:
            action["domain"] = [("id", "in", projects.ids)]
        elif len(projects) == 1:
            form_view = [
                (self.env.ref("odoo_project.odoo_project_view_form").id, "form")
            ]
            if "views" in action:
                action["views"] = form_view + [
                    (state, view) for state, view in action["views"] if view != "form"
                ]
            else:
                action["views"] = form_view
            action["res_id"] = projects.id
        else:
            action = {"type": "ir.actions.act_window_close"}

        context = {
            "default_repository_id": self.id,
        }
        action["context"] = context
        return action
