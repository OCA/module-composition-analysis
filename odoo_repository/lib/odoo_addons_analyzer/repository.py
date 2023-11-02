# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import glob
import os

from .module import ModuleAnalysis


class RepositoryAnalysis:
    def __init__(
        self,
        folder_path,
        languages=("Python", "XML", "CSS", "JavaScript"),
        name=None,
    ):
        self.folder_path = folder_path
        self.languages = languages
        self.name = os.path.basename(folder_path) if name is None else name

    @property
    def modules_paths(self):
        pattern1 = os.path.join(self.folder_path, "*", "__manifest__.py")
        pattern2 = os.path.join(self.folder_path, "*", "__openerp__.py")
        file_paths = glob.glob(pattern1) + glob.glob(pattern2)
        return [os.path.dirname(file_path) for file_path in file_paths]

    def to_dict(self):
        data = {}
        for module_path in self.modules_paths:
            module = os.path.basename(module_path)
            analysis = ModuleAnalysis(
                module_path, languages=self.languages, repo_analysis=self
            )
            data[module] = analysis.to_dict()
        return data
