# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.tests.common import Form

from odoo.addons.odoo_repository.tests import common


class Common(common.Common):
    def setUp(self):
        super().setUp()
        self.project = self.env["odoo.project"].create(
            {
                "name": "TEST",
                "odoo_version_id": self.branch.id,
            }
        )
        self.wiz_model = self.env["odoo.project.import.modules"]

    @classmethod
    def _run_import_modules(cls, project, modules_list_text, **kwargs):
        wiz_model = cls.env["odoo.project.import.modules"].with_context(
            default_odoo_project_id=project.id
        )
        with Form(wiz_model) as form:
            form.modules_list = modules_list_text
            wiz = form.save()
        wiz.action_import()
        return wiz
