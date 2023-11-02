# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import ast
import os
import pathlib

import pygount


class ModuleAnalysis:
    def __init__(
        self,
        folder_path,
        languages=("Python", "XML", "CSS", "JavaScript"),
        repo_analysis=None,
    ):
        self.folder_path = folder_path
        self.languages = languages
        self.repo_analysis = repo_analysis
        self.summary = pygount.ProjectSummary()
        self._run()

    @property
    def name(self):
        return os.path.basename(self.folder_path)

    @property
    def file_paths(self):
        return [
            os.path.join(dirpath, f)
            for (dirpath, dirnames, filenames) in os.walk(self.folder_path)
            for f in filenames
        ]

    @property
    def manifest(self):
        for manifest_name in ("__openerp__.py", "__manifest__.py"):
            manifest_path = pathlib.Path(self.folder_path, manifest_name)
            if manifest_path.exists():
                with open(manifest_path) as file_:
                    try:
                        manifest = ast.literal_eval(file_.read())
                    except ValueError:
                        return {}
                    return manifest
        return {}

    def _run(self):
        for file_path in self.file_paths:
            source_analysis = pygount.SourceAnalysis.from_file(
                file_path,
                group=os.path.basename(self.folder_path),
                encoding="utf-8",
            )
            self.summary.add(source_analysis)

    def to_dict(self):
        summaries = dict.fromkeys(self.languages, 0)
        data = {"code": summaries, "manifest": self.manifest}
        for summary in self.summary.language_to_language_summary_map.values():
            for language in self.languages:
                if not summary.language.startswith(language):
                    continue
                summaries[language] += summary.code_count
        return data
