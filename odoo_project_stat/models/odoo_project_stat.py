# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models
from odoo.tools.safe_eval import safe_eval


class OdooProjectStat(models.Model):
    _name = "odoo.project.stat"
    _description = "Odoo Project Stats"
    _rec_name = "name"
    _order = "odoo_project_id, date, sequence, name"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        ondelete="cascade",
        string="Project",
        index=True,
        required=True,
        readonly=True,
    )
    config_id = fields.Many2one(
        comodel_name="odoo.project.stat.config",
        ondelete="restrict",
        string="Project Stat Configuration",
        required=True,
        readonly=True,
    )
    date = fields.Date(required=True, index=True)
    sequence = fields.Integer(related="config_id.sequence", store=True)
    name = fields.Char(related="config_id.name", store=True)
    color = fields.Char(related="config_id.color")
    modules_count = fields.Integer(readonly=True)
    sloc = fields.Integer(string="Lines of code", readonly=True)

    _sql_constraints = [
        (
            "odoo_project_config_date_uniq",
            "UNIQUE (odoo_project_id, config_id, date)",
            "This project stats record already exists.",
        ),
    ]

    def _get_stats(self, odoo_project, date=None, config=None, limit=None):
        domain = [("odoo_project_id", "=", odoo_project.id)]
        if date:
            domain.append(("date", "=", date))
        if config:
            domain.append(("config_id", "=", config.id))
        return self.search(domain, limit=limit)

    def _generate_stats(self, odoo_project_id):
        """Generate the stats for a given `odoo_project_id`."""
        odoo_project = self.env["odoo.project"].browse(odoo_project_id).exists()
        odoo_project.ensure_one()
        modules = odoo_project.project_module_ids
        total_count = len(modules)
        total_sloc = (
            sum(modules.mapped("sloc_python"))
            + sum(modules.mapped("sloc_xml"))
            + sum(modules.mapped("sloc_js"))
            + sum(modules.mapped("sloc_css"))
        )
        # Clean up stats of today if any
        today = fields.Date.today()
        existing_stats = self._get_stats(odoo_project, date=today)
        existing_stats.sudo().unlink()
        # Create or update existing stat record
        configs = self.env["odoo.project.stat.config"].search([])
        for config in configs:
            stat = self._get_stats(odoo_project, date=today, config=config, limit=1)
            values = self._generate_stat_values(odoo_project, config, total_count)
            if stat:
                stat.sudo().write(values)
            else:
                self.sudo().create(values)
        stats = self._get_stats(odoo_project, date=today)
        stat_residual = stats.filtered(lambda o: o.config_id.residual)
        if stat_residual:
            other_stats = stats - stat_residual
            stat_residual.sudo().write(
                {
                    "modules_count": (
                        total_count - sum(other_stats.mapped("modules_count"))
                    ),
                    "sloc": (total_sloc - sum(other_stats.mapped("sloc"))),
                }
            )
        return True

    def _generate_stat_values(self, odoo_project, config, total_count):
        # Counter
        if config.residual:
            modules_count = 0
            sloc = 0
        else:
            domain = safe_eval(config.domain)
            # FIXME: use odoo.osv.expression.AND
            domain.append(("odoo_project_id", "=", odoo_project.id))
            modules = self.env["odoo.project.module"].search(domain)
            modules_count = len(modules)
            sloc = (
                sum(modules.mapped("sloc_python"))
                + sum(modules.mapped("sloc_xml"))
                + sum(modules.mapped("sloc_js"))
                + sum(modules.mapped("sloc_css"))
            )
        return {
            "odoo_project_id": odoo_project.id,
            "config_id": config.id,
            "date": fields.Date.today(),
            "modules_count": modules_count,
            "sloc": sloc,
        }
