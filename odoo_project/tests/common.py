# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.tests.common import Form

from odoo.addons.odoo_repository.tests import common


class ProjectCommon(common.Common):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["odoo.project"].create(
            {
                "name": "TEST",
                "odoo_version_id": cls.branch.id,
            }
        )
        cls.wiz_import_modules_model = cls.env["odoo.project.import.modules"]

    @classmethod
    def _run_import_modules(cls, project, modules_list_text, **kwargs):
        wiz_model = cls.wiz_import_modules_model.with_context(
            default_odoo_project_id=project.id
        )
        with Form(wiz_model) as form:
            form.modules_list = modules_list_text
            wiz = form.save()
        wiz.action_import()
        return wiz
