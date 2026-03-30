# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import io
import shutil
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

import git

cache = threading.local()


class OdooRepoMixin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.upstream_org = "ORG"
        cls.fork_org = "FORK"
        cls.repo_name = "test"
        cls.source1 = "origin/15.0"
        cls.source2 = "origin/16.0"
        cls.target1 = "origin/16.0"
        cls.target2 = "origin/17.0"
        cls.target3 = "origin/18.0"
        cls.addon = "my_module"
        cls.target_addon = "my_module_renamed"
        # Create a temporary Git repository
        cls.repo_upstream_path = cls._get_upstream_repository_path()
        cls.addon_path = Path(cls.repo_upstream_path) / cls.addon
        cls.manifest_path = cls.addon_path / "__manifest__.py"

    @classmethod
    def _get_upstream_repository_path(cls) -> Path:
        """Returns the path of upstream repository.

        Generate the upstream git repository or re-use the one put in cache if any.
        """
        if hasattr(cache, "archive_data") and cache.archive_data:
            # Unarchive the repository from memory
            repo_path = cls._unarchive_upstream_repository(cache.archive_data)
        else:
            # Prepare and archive the repository in memory
            repo_path = cls._create_tmp_git_repository()
            addon_path = repo_path / cls.addon
            cls._fill_git_repository(repo_path, addon_path)
            cache.archive_data = cls._archive_upstream_repository(repo_path)
        return repo_path

    @classmethod
    def _archive_upstream_repository(cls, repo_path: Path) -> bytes:
        """Archive the repository located at `repo_path`.

        Returns binary value of the archive.
        """
        # Create in-memory zip archive
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for file_path in repo_path.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(repo_path)
                    zipf.write(file_path, arcname)
        return zip_buffer.getvalue()

    @classmethod
    def _unarchive_upstream_repository(cls, archive_data: bytes) -> Path:
        """Unarchive the repository contained in `archive_data`.

        Returns path of repository.
        """
        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(io.BytesIO(archive_data), "r") as zip_ref:
            zip_ref.extractall(temp_dir)
        # Look for the repo directory and return its path
        for path in Path(temp_dir).rglob("*"):
            if path.is_dir() and ".git" in path.name:
                return path.parent

    @classmethod
    def _create_tmp_git_repository(cls) -> Path:
        """Create a temporary Git repository to run tests."""
        repo_path = tempfile.mkdtemp()
        repo = git.Repo.init(repo_path)
        repo.config_writer().set_value("user", "name", "test").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()
        return Path(repo_path)

    @classmethod
    def _fill_git_repository(cls, repo_path: Path, addon_path: Path):
        """Create branches with some content in the Git repository."""
        repo = git.Repo(repo_path)
        # Commit a file in '15.0'
        branch1 = cls.source1.split("/")[1]
        repo.git.checkout("--orphan", branch1)
        cls._create_module(addon_path)
        repo.index.add(addon_path)
        commit = repo.index.commit(f"[ADD] {cls.addon}")
        # Port the commit from 15.0 to 16.0
        branch2 = cls.source2.split("/")[1]
        repo.git.checkout("--orphan", branch2)
        repo.git.reset("--hard")
        # Some git operations do not appear to be atomic, so a delay is added
        # to allow them to complete
        time.sleep(1)
        repo.git.cherry_pick(commit.hexsha)
        # Create an empty branch 17.0
        branch3 = cls.target2.split("/")[1]
        repo.git.checkout("--orphan", branch3)
        repo.git.reset("--hard")
        repo.git.commit("-m", "Init", "--allow-empty")
        # Port the commit from 15.0 to 18.0
        branch4 = cls.target3.split("/")[1]
        repo.git.checkout("--orphan", branch4)
        repo.git.reset("--hard")
        time.sleep(1)
        repo.git.cherry_pick(commit.hexsha)
        # Rename the module on 18.0
        repo.git.mv(cls.addon, cls.target_addon)
        repo.git.commit("-m", f"Rename {cls.addon} to {cls.target_addon}")

    @classmethod
    def _create_module(cls, module_path: Path):
        manifest_lines = [
            "# Copyright 2026 Sébastien Alix\n",
            "# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)\n",
            "{\n",
            '    "name": "Test",\n',
            '    "version": "1.0.0",\n',
            '    "category": "Test Module",\n',
            '    "author": "Odoo Community Association (OCA)",\n',
            '    "website": "https://github.com/OCA/module-composition-analysis",\n',
            '    "license": "AGPL-3",\n',
            '    "depends": ["base"],\n',
            '    "data": [],\n',
            '    "demo": [],\n',
            '    "installable": True,\n',
            "}\n",
        ]
        module_path.mkdir(parents=True, exist_ok=True)
        manifest_path = module_path / "__manifest__.py"
        with open(manifest_path, "w") as manifest:
            manifest.writelines(manifest_lines)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Clean up upstream Git repository
        shutil.rmtree(cls.repo_upstream_path)
