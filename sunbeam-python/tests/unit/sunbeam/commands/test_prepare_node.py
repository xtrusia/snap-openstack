# SPDX-FileCopyrightText: 2026 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

import subprocess

import pytest

from sunbeam.commands.prepare_node import COMMON_TEMPLATE


@pytest.mark.parametrize("install_status", [0, 42])
def test_juju_install_status(tmp_path, install_status):
    script = (
        """
command() { if [ "$1 $2" = '-v juju' ]; then return 1; fi; builtin command "$@"; }
sudo() {
    if [ "$1 $2" = 'snap install' ]; then return "$INSTALL_STATUS"; fi
    echo "sudo $*"
}
snap() { echo 'openstack 1 1 2026.1/stable'; }
"""
        + COMMON_TEMPLATE
    )
    result = subprocess.run(
        ["bash"],
        input=script,
        text=True,
        capture_output=True,
        env={"HOME": str(tmp_path), "INSTALL_STATUS": str(install_status)},
        check=False,
    )
    assert result.returncode == install_status
    assert ("snap refresh --hold openstack" in result.stdout) == (install_status == 0)
