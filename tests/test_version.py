from importlib.metadata import version

import openbot_sdk


def test_runtime_version_matches_package_metadata() -> None:
    assert openbot_sdk.__version__ == version("openbot-sdk")


def test_v002_public_resources_are_exported() -> None:
    assert {"DataUpload", "DataArtifact", "DataUploadError"}.issubset(openbot_sdk.__all__)
