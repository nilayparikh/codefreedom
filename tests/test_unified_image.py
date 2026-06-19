"""Tests for Docker image constants and configuration."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestDefaultImageConstants:
    """Verify all agent modules point to tool-agnostic image tags."""

    def test_mimo_default_image_uses_platform_tag(self):
        from codefreedom.cli.mimo import DEFAULT_MIMO_IMAGE
        assert DEFAULT_MIMO_IMAGE == "docker.io/nilayparikh/codefreedom:ubuntu-latest"

    def test_opencode_default_image_uses_platform_tag(self):
        from codefreedom.cli.opencode import DEFAULT_OPENCODE_IMAGE
        assert DEFAULT_OPENCODE_IMAGE == "docker.io/nilayparikh/codefreedom:ubuntu-latest"

    def test_launcher_default_tag_uses_platform_tag(self):
        from codefreedom.launcher import IMAGE_TAG
        assert IMAGE_TAG == "ubuntu-latest"

    def test_launcher_target_image_uses_platform_tag(self):
        from codefreedom.launcher import TARGET_IMAGE
        assert TARGET_IMAGE == "docker.io/nilayparikh/codefreedom:ubuntu-latest"


class TestSandboxImagesSchema:
    """Verify SandboxImages schema supports unified key."""

    def test_unified_field_accepted(self):
        from codefreedom.schemas.profiles import SandboxImages

        images = SandboxImages(
            default="test:latest",
            unified="custom:latest",
            cuda="cuda:latest",
            rocm="rocm:latest",
        )
        assert images.unified == "custom:latest"

    def test_unified_field_optional(self):
        from codefreedom.schemas.profiles import SandboxImages

        images = SandboxImages(default="test:latest")
        assert images.unified is None

    def test_all_fields_together(self):
        from codefreedom.schemas.profiles import SandboxImages

        images = SandboxImages(
            default="default:latest",
            unified="custom:latest",
            cuda="cuda:latest",
            rocm="rocm:latest",
        )
        assert images.default == "default:latest"
        assert images.unified == "custom:latest"
        assert images.cuda == "cuda:latest"
        assert images.rocm == "rocm:latest"


class TestGpuFlags:
    """Verify GPU flags are registered on all agent modules."""

    def test_mimo_register_args_has_cuda_rocm(self):
        import argparse
        from codefreedom.cli.mimo import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox", "--cuda"])
        assert args.gpu_cuda is True
        assert args.gpu_rocm is False

    def test_mimo_register_args_has_rocm(self):
        import argparse
        from codefreedom.cli.mimo import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox", "--rocm"])
        assert args.gpu_cuda is False
        assert args.gpu_rocm is True

    def test_opencode_register_args_has_cuda_rocm(self):
        import argparse
        from codefreedom.cli.opencode import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox", "--cuda"])
        assert args.gpu_cuda is True
        assert args.gpu_rocm is False

    def test_opencode_register_args_has_rocm(self):
        import argparse
        from codefreedom.cli.opencode import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        args = parser.parse_args(["--sandbox", "--rocm"])
        assert args.gpu_cuda is False
        assert args.gpu_rocm is True

    def test_cuda_rocm_mutually_exclusive_mimo(self):
        import argparse
        from codefreedom.cli.mimo import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--cuda", "--rocm"])

    def test_cuda_rocm_mutually_exclusive_opencode(self):
        import argparse
        from codefreedom.cli.opencode import register_args

        parser = argparse.ArgumentParser()
        register_args(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--cuda", "--rocm"])
