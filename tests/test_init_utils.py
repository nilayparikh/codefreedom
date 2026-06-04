"""Tests for shared init_utils module."""

from codefreedom.cli.init_utils import copy_bundled_files, find_bundled_examples


class TestFindBundledExamples:
    def test_returns_examples_dir(self):
        result = find_bundled_examples(__file__)
        assert result.name == "examples"
        assert result.parent.name == "codefreedom"


class TestCopyBundledFiles:
    def test_copies_new_files(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        (src / "sub").mkdir(parents=True)
        (src / "a.txt").write_text("hello")
        (src / "sub" / "b.txt").write_text("world")

        created = copy_bundled_files(src, dst, label="test")
        assert len(created) == 2
        assert (dst / "a.txt").read_text() == "hello"
        assert (dst / "sub" / "b.txt").read_text() == "world"

    def test_skips_all_when_any_exists(self, tmp_path):
        """All-or-nothing: if any destination file exists, nothing is copied."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        (src / "sub").mkdir(parents=True)
        (src / "a.txt").write_text("new")
        (src / "sub" / "b.txt").write_text("new-sub")
        dst.mkdir()
        (dst / "a.txt").write_text("existing")
        # b.txt does not exist yet, but a.txt does — should skip everything

        created = copy_bundled_files(src, dst, label="test")
        assert len(created) == 0
        assert (dst / "a.txt").read_text() == "existing"  # unchanged
        assert not (dst / "sub" / "b.txt").exists()  # not created

    def test_empty_dst_dir_copies_all(self, tmp_path):
        """If dst dir exists but is empty, all files are copied."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "a.txt").write_text("hello")

        created = copy_bundled_files(src, dst, label="test")
        assert len(created) == 1
        assert (dst / "a.txt").read_text() == "hello"

    def test_nonexistent_dst_dir_copies_all(self, tmp_path):
        """If dst dir does not exist, all files are copied."""
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        (src / "a.txt").write_text("hello")

        created = copy_bundled_files(src, dst, label="test")
        assert len(created) == 1
        assert (dst / "a.txt").read_text() == "hello"
