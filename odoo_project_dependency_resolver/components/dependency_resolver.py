# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import dataclasses

from odoo.addons.component.core import AbstractComponent


@dataclasses.dataclass(frozen=True)
class ResolvedDependency:
    """A module declared by a project, as read from a dependency file."""

    module_name: str
    version: str = None
    clone_url: str = None
    ref: str = None
    subdirectory: str = None

    @property
    def is_pinned(self):
        """Whether the module is frozen on a specific revision."""
        return bool(self.clone_url and self.ref)


class DependencyResolver(AbstractComponent):
    """Turn the content of a dependency file into a list of modules.

    Concrete resolvers only deal with text: they parse what they are given
    and return what they found, without ever touching the ORM. Mapping the
    result onto modules of the database is the job of `odoo.project`, and is
    shared by every format.

    Adding support for another format (pip.lock, uv.lock...) is therefore a
    matter of adding a component named after the format, and an entry in the
    `dependency_resolver` selection of `odoo.project`.
    """

    _name = "project.dependency.resolver"
    _collection = "odoo.mca.backend"

    def resolve(self, content):
        """Return the `ResolvedDependency` list declared in `content`."""
        raise NotImplementedError
