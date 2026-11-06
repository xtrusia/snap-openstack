# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

from stat import S_IMODE
from types import SimpleNamespace

import yaml

from sunbeam.core.deployments import SHARE_PATH, store_deployment_as_yaml


def test_export_does_not_overwrite_existing_files(tmp_path):
    directory = tmp_path / SHARE_PATH
    directory.mkdir(parents=True)
    config = directory / "deployments.yaml"
    config.write_text("active: deployments\ndeployments: []\n")
    snap = SimpleNamespace(paths=SimpleNamespace(real_home=tmp_path))
    deployment = SimpleNamespace(
        name="deployments", dict=lambda: {"name": "deployments", "type": "maas"}
    )

    exported = store_deployment_as_yaml(snap, deployment)

    assert config.read_text() == "active: deployments\ndeployments: []\n"
    assert exported == directory / "deployment-exports" / "deployments.yaml"
    assert S_IMODE(exported.stat().st_mode) == 0o600
    assert yaml.safe_load(exported.read_text())["name"] == "deployments"
