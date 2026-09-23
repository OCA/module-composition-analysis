# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import re
from urllib.parse import parse_qs, urlparse, urlunparse

from packaging.requirements import InvalidRequirement, Requirement

from odoo.addons.component.core import Component

from .dependency_resolver import ResolvedDependency

# Odoo addons are distributed as 'odoo-addon-<module>' since 15.0, and as
# 'odoo<series>-addon-<module>' before. Note that this excludes packages such
# as 'odoo-addons-parser', which are not addons.
ADDON_PREFIX_RE = re.compile(r"^odoo(?:\d+)?-addon-", re.IGNORECASE)
# Comments, but not the '#subdirectory=' fragment of a URL
COMMENT_RE = re.compile(r"(^|\s)#.*$")
HASH_RE = re.compile(r"\s--hash=\S+")
# An Odoo manifest version holds 5 segments ('<series>.<x>.<y>.<z>.<w>').
# setuptools-odoo appends a serial to it when only the packaging changed,
# e.g. addon '18.0.1.2.0' published as wheel '18.0.1.2.0.3'.
MANIFEST_VERSION_SEGMENTS = 5


class RequirementsTxtResolver(Component):
    """Resolve the modules of a project from a pip requirements file."""

    _name = "project.dependency.resolver.requirements_txt"
    _inherit = "project.dependency.resolver"
    _usage = "project.dependency.resolver.requirements_txt"

    def resolve(self, content):
        dependencies = []
        for requirement in self._iter_requirements(content):
            dependency = self._parse_requirement(requirement)
            if dependency:
                dependencies.append(dependency)
        return dependencies

    def _iter_requirements(self, content):
        """Yield the requirement lines."""
        buffer = ""
        for raw_line in content.splitlines():
            line = COMMENT_RE.sub("", raw_line).strip()
            if not line:
                continue
            if line.endswith("\\"):
                buffer += line[:-1].strip() + " "
                continue
            line, buffer = buffer + line, ""
            if line.startswith("-"):
                # Options ('-r', '-c', '--index-url'...)
                continue
            line = HASH_RE.sub("", line)
            # Remove environment markers ('; python_version < "3.8"')
            # and trailing whitespace
            line = line.split(";", 1)[0].strip()
            if line:
                yield line

    def _parse_requirement(self, requirement):
        """Return the `ResolvedDependency` of a requirement, if it is an addon."""
        requirement = requirement.strip()
        if not requirement:
            return None

        try:
            req = Requirement(requirement)
        except InvalidRequirement:
            # Fallback for non-PEP 508 lines that pip still accepts in practice.
            # vcs legacy line ex:
            # git+https://github.com/OCA/project.git@v1.2.3#egg=odoo-addon-project
            name = re.split(r"[<>=!~\[\s]", requirement, maxsplit=1)[0]
            module_name = self._get_module_name(name)
            return ResolvedDependency(module_name) if module_name else None

        name = req.name
        module_name = self._get_module_name(name)
        if not module_name:
            return None
        if req.url:
            return self._parse_direct_reference(name, req.url)

        version = str(req.specifier).strip()
        if version.startswith("=="):
            return ResolvedDependency(
                module_name,
                version=self._to_manifest_version(version[2:].strip()),
            )

        # Anything else (ranges, unpinned...) carries no usable version.
        return ResolvedDependency(module_name)

    def _parse_direct_reference(self, name, url):
        """Return the `ResolvedDependency` of a module pinned on a repository."""
        module_name = self._get_module_name(name)
        if not module_name:
            return None
        url, __, fragment = url.partition("#")
        subdirectory = self._get_subdirectory(fragment)
        clone_url, ref = self._split_vcs_url(url)
        return ResolvedDependency(
            module_name,
            clone_url=clone_url,
            ref=ref,
            subdirectory=subdirectory,
        )

    def _get_module_name(self, distribution_name):
        """Return the technical name of the module packaged as `distribution_name`.

        Returns nothing when the distribution is not an Odoo addon.
        """
        if not ADDON_PREFIX_RE.match(distribution_name):
            return None
        # Odoo module names never hold a dash, so undoing the normalization
        # performed by the packaging is unambiguous
        return ADDON_PREFIX_RE.sub("", distribution_name).replace("-", "_")

    @staticmethod
    def _get_subdirectory(fragment):
        """Return the 'subdirectory' held by the fragment of a requirement URL."""
        values = parse_qs(fragment).get("subdirectory")
        return values[0] if values else None

    @staticmethod
    def _split_vcs_url(url):
        """Return the `(clone_url, ref)` parts of a VCS requirement URL.

        The revision is split off the path rather than off the whole URL, so
        that credentials held by the network location ('https://user@host/...')
        are not mistaken for one.
        """
        url = re.sub(r"^\w+\+", "", url)
        parts = urlparse(url)
        path, __, ref = parts.path.rpartition("@")
        if not path:
            # No revision pinned
            return (url, None)
        return (urlunparse(parts._replace(path=path)), ref)

    @staticmethod
    def _to_manifest_version(version):
        """Return the manifest version a distribution version was built from."""
        # Drop the PEP 440 local and post segments added by the packaging
        version = re.split(r"[+!]", version)[0]
        segments = version.split(".")
        if len(segments) > MANIFEST_VERSION_SEGMENTS:
            return ".".join(segments[:MANIFEST_VERSION_SEGMENTS])
        return version
