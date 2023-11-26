# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)


def adapt_version(major_version: str, module_version: str):
    """Return the module version prefixed with major version.

    This function has been copied and adapted from upstream Odoo source code:
        https://github.com/odoo/odoo/blob/16.0/odoo/modules/module.py#L527-L533
    """
    # Remove extra special characters (e.g. '14.0.' => '14.0')
    # NOTE: we need to sanitize such versions in order to compute a
    # sequence number helping the sort of module versions.
    chars = ["."]
    for char in chars:
        while module_version.startswith(char):
            module_version = module_version[1:]
        while module_version.endswith(char):
            module_version = module_version[:-1]
    # Append major Odoo version as prefix if needed
    if module_version == major_version or not module_version.startswith(
        major_version + "."
    ):
        module_version = "%s.%s" % (major_version, module_version)
    return module_version
