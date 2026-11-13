# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import plotly.graph_objects as go
from plotly.offline import plot

from odoo import fields, models


class OdooProject(models.Model):
    _inherit = "odoo.project"

    stats_ids = fields.One2many(
        comodel_name="odoo.project.stat",
        inverse_name="odoo_project_id",
    )
    chart_modules_count = fields.Text(
        string="Modules Chart",
        compute="_compute_charts",
    )
    chart_sloc = fields.Text(
        string="Lines of Code Chart",
        compute="_compute_charts",
    )

    def _get_last_stats(self):
        self.ensure_one()
        last_stat = self.env["odoo.project.stat"].search(
            [("odoo_project_id", "=", self.id)],
            order="date DESC",
            limit=1,
        )
        if not last_stat:
            return self.env["odoo.project.stat"].browse()
        return self.env["odoo.project.stat"].search(
            [("odoo_project_id", "=", self.id), ("date", "=", last_stat.date)],
            order="sequence",
        )

    def _compute_charts(self):
        for rec in self:
            rec.chart_modules_count = rec.chart_sloc = False
            stats = rec._get_last_stats()
            labels = stats.mapped("name")
            colors = stats.mapped("color")
            count_values = stats.mapped("modules_count")
            sloc_values = stats.mapped("sloc")
            # Modules Count Pie Chart
            if count_values:
                count_chart = go.Figure(
                    data=[
                        go.Pie(
                            labels=labels,
                            values=count_values,
                        )
                    ]
                )
                self._chart_update_layout(count_chart, colors=colors, title="Modules")
                rec.chart_modules_count = plot(
                    count_chart,
                    include_plotlyjs=False,
                    output_type="div",
                    config={"displaylogo": False},
                )
            # SLOC Pie Chart
            if sloc_values:
                sloc_chart = go.Figure(
                    data=[
                        go.Pie(
                            labels=labels,
                            values=sloc_values,
                        )
                    ]
                )
                self._chart_update_layout(
                    sloc_chart, colors=colors, title="Lines of Code"
                )
                rec.chart_sloc = plot(
                    sloc_chart,
                    include_plotlyjs=False,
                    output_type="div",
                    config={"displaylogo": False},
                )

    def _chart_update_layout(self, chart, colors=None, title=None):
        chart.update_traces(
            textinfo="percent+label",
            textposition="inside",
            hole=0.35,
            sort=False,
            direction="clockwise",
            rotation=180,
        )
        if colors:
            chart.update_traces(marker=dict(colors=colors))
        if title:
            chart.update_layout(title_text=title, title_x=0.5, title_y=0.5)
        chart.update_layout(
            margin=dict(l=0, r=0, t=20, b=20),
            showlegend=False,
            autosize=False,
            width=450,
            height=450,
        )

    def action_generate_stats(self):
        for rec in self:
            self.env["odoo.project.stat"].sudo()._generate_stats(rec.id)
        return True
