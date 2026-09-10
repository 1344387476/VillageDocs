from pathlib import Path

from housebook.paths import default_workspace_root, install_root


def test_development_workspace_uses_resource_beside_project() -> None:
    assert default_workspace_root() == install_root() / "resource"
    assert default_workspace_root().name == "resource"
    assert isinstance(default_workspace_root(), Path)
