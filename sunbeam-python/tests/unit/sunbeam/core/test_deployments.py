# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

import pytest
import yaml

from sunbeam.core.deployments import DeploymentsConfig


def test_write_preserves_existing_config_when_replace_fails(tmp_path, mocker):
    path = tmp_path / "deployments.yaml"
    original = "active: mycloud\ndeployments: []\n"
    path.write_text(original)
    config = DeploymentsConfig.load(path)
    mocker.patch(
        "sunbeam.core.deployments.os.replace",
        side_effect=OSError("replace failed"),
    )

    with pytest.raises(OSError, match="replace failed"):
        config.write()

    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]


def test_write_replaces_config_on_success(tmp_path):
    path = tmp_path / "deployments.yaml"
    path.write_text("active: old\ndeployments: []\n")
    config = DeploymentsConfig.load(path)
    config.active = "new"

    config.write()

    assert yaml.safe_load(path.read_text()) == {"active": "new", "deployments": []}
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]
