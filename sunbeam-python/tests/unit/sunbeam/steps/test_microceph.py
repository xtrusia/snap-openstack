# SPDX-FileCopyrightText: 2023 - Canonical Ltd
# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import Mock

from sunbeam.core.common import ResultType
from sunbeam.core.juju import ActionFailedException, ExecFailedException
from sunbeam.steps.microceph import (
    ConfigureMicrocephOSDStep,
    RemoveMicrocephOSDsStep,
    SetCephMgrPoolSizeStep,
)


def _command_result(stdout="", return_code=0, stderr=""):
    return Mock(stdout=stdout, return_code=return_code, stderr=stderr)


def _configured_disks(disks):
    return json.dumps({"ConfiguredDisks": disks})


def _crush_tree(children=None):
    nodes = (
        []
        if children is None
        else [{"name": "node-1", "type": "host", "children": children}]
    )
    return json.dumps({"nodes": nodes})


def _cleanup_step(cclient, jhelper, force=False):
    cclient.cluster.get_node_info.return_value = {
        "machineid": "1",
        "role": "storage",
    }
    jhelper.get_machines.return_value = {
        "1": Mock(hostname="node-1"),
        "2": Mock(hostname="node-2"),
    }
    jhelper.get_application.return_value = Mock(
        units={"microceph/0": Mock(machine="1"), "microceph/1": Mock(machine="2")}
    )
    return RemoveMicrocephOSDsStep(
        cclient,
        "node-1",
        jhelper,
        "test-model",
        force=force,
    )


class TestConfigureMicrocephOSDStep:
    def test_is_skip(self, cclient, jhelper, step_context):
        step = ConfigureMicrocephOSDStep(cclient, "test-0", jhelper, "test-model")
        step.disks = "/dev/sdb,/dev/sdc"
        result = step.is_skip(step_context)

        assert result.result_type == ResultType.COMPLETED

    def test_run(self, cclient, jhelper, step_context):
        step = ConfigureMicrocephOSDStep(cclient, "test-0", jhelper, "test-model")
        step.disks = "/dev/sdb,/dev/sdc"
        step.wipe = False
        result = step.run(step_context)

        jhelper.run_action.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_action_failed(self, cclient, jhelper, step_context):
        jhelper.run_action.side_effect = ActionFailedException("Action failed...")

        step = ConfigureMicrocephOSDStep(cclient, "test-0", jhelper, "test-model")
        step.disks = "/dev/sdb,/dev/sdc"
        result = step.run(step_context)

        jhelper.run_action.assert_called_once()
        expected_message = (
            f"Microceph Adding disks {step.disks} failed: Action failed..."
        )
        assert result.result_type == ResultType.FAILED
        assert result.message == expected_message

    def test_run_with_already_added_disks(self, cclient, jhelper, step_context):
        error_msg = (
            "[{'spec': '/dev/sdb', 'status': 'failure', 'message': 'Error: failed"
            'to record disk: This "disks" entry already exists\\n\'}]'
        )
        error_result = {"result": error_msg, "return-code": 0}
        jhelper.run_action.side_effect = ActionFailedException(error_result)

        step = ConfigureMicrocephOSDStep(cclient, "test-0", jhelper, "test-model")
        step.disks = "/dev/sdb"
        step.wipe = False
        result = step.run(step_context)

        jhelper.run_action.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_with_wipe_true(self, cclient, jhelper, step_context):
        step = ConfigureMicrocephOSDStep(cclient, "test-0", jhelper, "test-model")
        step.disks = "/dev/sdb,/dev/sdc"
        step.wipe = True
        jhelper.get_unit_from_machine = Mock(return_value="unit/0")
        jhelper.run_action = Mock(return_value={"status": "completed"})
        result = step.run(step_context)

        jhelper.run_action.assert_called_once_with(
            "unit/0",
            "test-model",
            "add-osd",
            action_params={"device-id": "/dev/sdb,/dev/sdc", "wipe": True},
        )
        assert result.result_type == ResultType.COMPLETED

    def test_run_with_wipe_false(self, cclient, jhelper, step_context):
        step = ConfigureMicrocephOSDStep(cclient, "test-0", jhelper, "test-model")
        step.disks = "/dev/sdb,/dev/sdc"
        step.wipe = False
        jhelper.get_unit_from_machine = Mock(return_value="unit/0")
        jhelper.run_action = Mock(return_value={"status": "completed"})
        result = step.run(step_context)

        jhelper.run_action.assert_called_once_with(
            "unit/0",
            "test-model",
            "add-osd",
            action_params={"device-id": "/dev/sdb,/dev/sdc"},
        )
        assert result.result_type == ResultType.COMPLETED


class TestRemoveMicrocephOSDsStep:
    def test_run_removes_sorted_db_osds_and_verifies_both_sources(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [
                        {"osd": 5, "location": "node-1", "path": "/dev/sdc"},
                        {"osd": 2, "location": "node-1", "path": "/dev/sdb"},
                    ]
                )
            ),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": [5, 2]}]}
                )
            ),
            _command_result(),
            _command_result(),
            _command_result(stdout=_configured_disks([])),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": []}]}
                )
            ),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        result = step.run(step_context)

        assert result.result_type == ResultType.COMPLETED
        assert [
            call.args[2]
            for call in jhelper.run_cmd_on_machine_unit_payload.call_args_list
        ] == [
            "microceph disk list --json",
            "microceph.ceph osd tree --format json",
            "microceph disk remove osd.2 --timeout 1800",
            "microceph disk remove osd.5 --timeout 1800",
            "microceph disk list --json",
            "microceph.ceph osd tree --format json",
        ]

    def test_crush_only_osd_fails_before_any_removal(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(stdout=_configured_disks([])),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": [7]}]}
                )
            ),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        result = step.run(step_context)

        assert result.result_type == ResultType.FAILED
        assert jhelper.run_cmd_on_machine_unit_payload.call_count == 2

    def test_db_and_crush_mismatch_fails_before_any_removal(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [{"osd": 2, "location": "node-1", "path": "/dev/sdb"}]
                )
            ),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": [2, 7]}]}
                )
            ),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        result = step.run(step_context)

        assert result.result_type == ResultType.FAILED
        assert jhelper.run_cmd_on_machine_unit_payload.call_count == 2

    def test_force_keeps_safety_flags_only_on_remove_command(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper, force=True)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [{"osd": 2, "location": "node-1", "path": "/dev/sdb"}]
                )
            ),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": [2]}]}
                )
            ),
            _command_result(),
            _command_result(stdout=_configured_disks([])),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": []}]}
                )
            ),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        assert step.run(step_context).result_type == ResultType.COMPLETED
        command = jhelper.run_cmd_on_machine_unit_payload.call_args_list[2].args[2]
        assert command == (
            "microceph disk remove osd.2 --timeout 1800 "
            "--confirm-failure-domain-downgrade --bypass-safety-checks"
        )

    def test_force_does_not_ignore_failed_command(self, cclient, jhelper, step_context):
        step = _cleanup_step(cclient, jhelper, force=True)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [{"osd": 2, "location": "node-1", "path": "/dev/sdb"}]
                )
            ),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": [2]}]}
                )
            ),
            _command_result(return_code=1, stderr="busy"),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        assert step.run(step_context).result_type == ResultType.FAILED

    def test_force_does_not_ignore_exec_failure(self, cclient, jhelper, step_context):
        step = _cleanup_step(cclient, jhelper, force=True)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [{"osd": 2, "location": "node-1", "path": "/dev/sdb"}]
                )
            ),
            _command_result(
                stdout=json.dumps(
                    {"nodes": [{"name": "node-1", "type": "host", "children": [2]}]}
                )
            ),
            ExecFailedException("transport failed"),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        assert step.run(step_context).result_type == ResultType.FAILED

    def test_last_target_unit_is_allowed_as_cleanup_fallback(
        self, cclient, jhelper, step_context
    ):
        cclient.cluster.get_node_info.return_value = {
            "machineid": "1",
            "role": "storage",
        }
        jhelper.get_machines.return_value = {"1": Mock(hostname="node-1")}
        jhelper.get_application.return_value = Mock(
            units={"microceph/0": Mock(machine="1")}
        )
        step = RemoveMicrocephOSDsStep(cclient, "node-1", jhelper, "test-model")

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        assert step.unit == "microceph/0"

    def test_no_unit_fails_closed(self, cclient, jhelper, step_context):
        cclient.cluster.get_node_info.return_value = {
            "machineid": "1",
            "role": "storage",
        }
        jhelper.get_machines.return_value = {"1": Mock(hostname="node-1")}
        jhelper.get_application.return_value = Mock(units={})
        step = RemoveMicrocephOSDsStep(cclient, "node-1", jhelper, "test-model")

        result = step.is_skip(step_context)

        assert result.result_type == ResultType.FAILED

    def test_unknown_machine_fails_closed(self, cclient, jhelper, step_context):
        cclient.cluster.get_node_info.return_value = {
            "machineid": "1",
            "role": "storage",
        }
        jhelper.get_machines.return_value = {"1": Mock(hostname="node-1")}
        jhelper.get_application.return_value = Mock(
            units={"microceph/0": Mock(machine="unknown")}
        )
        step = RemoveMicrocephOSDsStep(cclient, "node-1", jhelper, "test-model")

        result = step.is_skip(step_context)

        assert result.result_type == ResultType.FAILED

    def test_unknown_machine_fails_closed_even_with_surviving_unit(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        jhelper.get_application.return_value = Mock(
            units={
                "microceph/0": Mock(machine="1"),
                "microceph/1": Mock(machine="2"),
                "microceph/2": Mock(machine="unknown"),
            }
        )

        result = step.is_skip(step_context)

        assert result.result_type == ResultType.FAILED
        jhelper.run_cmd_on_machine_unit_payload.assert_not_called()

    def test_db_only_osd_is_removed_when_crush_host_is_absent(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [{"osd": 2, "location": "node-1", "path": "/dev/sdb"}]
                )
            ),
            _command_result(stdout=_crush_tree()),
            _command_result(),
            _command_result(stdout=_configured_disks([])),
            _command_result(stdout=_crush_tree()),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        result = step.run(step_context)

        assert result.result_type == ResultType.COMPLETED
        commands = [
            call.args[2]
            for call in jhelper.run_cmd_on_machine_unit_payload.call_args_list
        ]
        assert "microceph disk remove osd.2 --timeout 1800" in commands
        assert not any(
            "purge" in command or "crush remove" in command for command in commands
        )

    def test_malformed_json_fails_before_removal(self, cclient, jhelper, step_context):
        step = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.return_value = _command_result(
            stdout="not-json"
        )

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        result = step.run(step_context)

        assert result.result_type == ResultType.FAILED
        assert jhelper.run_cmd_on_machine_unit_payload.call_count == 1

    def test_remaining_db_and_crush_osds_fail_after_removal(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        configured = _configured_disks(
            [{"osd": 2, "location": "node-1", "path": "/dev/sdb"}]
        )
        tree = _crush_tree([2])
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(stdout=configured),
            _command_result(stdout=tree),
            _command_result(),
            _command_result(stdout=configured),
            _command_result(stdout=tree),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        result = step.run(step_context)

        assert result.result_type == ResultType.FAILED
        commands = [
            call.args[2]
            for call in jhelper.run_cmd_on_machine_unit_payload.call_args_list
        ]
        assert commands.count("microceph disk remove osd.2 --timeout 1800") == 1

    def test_partial_retry_removes_only_remaining_db_osd(
        self, cclient, jhelper, step_context
    ):
        step = _cleanup_step(cclient, jhelper)
        configured = _configured_disks(
            [
                {"osd": 2, "location": "node-1", "path": "/dev/sdb"},
                {"osd": 5, "location": "node-1", "path": "/dev/sdc"},
            ]
        )
        tree = _crush_tree([2, 5])
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(stdout=configured),
            _command_result(stdout=tree),
            _command_result(),
            _command_result(return_code=1, stderr="busy"),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        assert step.run(step_context).result_type == ResultType.FAILED

        retry = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.reset_mock()
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(
                stdout=_configured_disks(
                    [{"osd": 5, "location": "node-1", "path": "/dev/sdc"}]
                )
            ),
            _command_result(stdout=_crush_tree([5])),
            _command_result(),
            _command_result(stdout=_configured_disks([])),
            _command_result(stdout=_crush_tree()),
        ]

        assert retry.is_skip(step_context).result_type == ResultType.COMPLETED
        assert retry.run(step_context).result_type == ResultType.COMPLETED
        commands = [
            call.args[2]
            for call in jhelper.run_cmd_on_machine_unit_payload.call_args_list
        ]
        assert commands.count("microceph disk remove osd.5 --timeout 1800") == 1
        assert "microceph disk remove osd.2 --timeout 1800" not in commands

    def test_clean_state_is_idempotent(self, cclient, jhelper, step_context):
        step = _cleanup_step(cclient, jhelper)
        jhelper.run_cmd_on_machine_unit_payload.side_effect = [
            _command_result(stdout=_configured_disks([])),
            _command_result(stdout=json.dumps({"nodes": []})),
        ]

        assert step.is_skip(step_context).result_type == ResultType.COMPLETED
        assert step.run(step_context).result_type == ResultType.COMPLETED
        assert [
            call.args[2]
            for call in jhelper.run_cmd_on_machine_unit_payload.call_args_list
        ] == [
            "microceph disk list --json",
            "microceph.ceph osd tree --format json",
        ]


class TestSetCephMgrPoolSizeStep:
    def test_is_skip(self, cclient, jhelper, step_context):
        cclient.cluster.list_nodes_by_role.return_value = []
        step = SetCephMgrPoolSizeStep(cclient, jhelper, "test-model")
        result = step.is_skip(step_context)

        assert result.result_type == ResultType.SKIPPED

    def test_is_skip_with_storage_nodes(self, cclient, jhelper, step_context):
        cclient.cluster.list_nodes_by_role.return_value = ["sunbeam1"]
        step = SetCephMgrPoolSizeStep(cclient, jhelper, "test-model")
        result = step.is_skip(step_context)

        assert result.result_type == ResultType.COMPLETED

    def test_run(self, cclient, jhelper, step_context):
        jhelper.run_action.return_value = Mock()
        step = SetCephMgrPoolSizeStep(cclient, jhelper, "test-model")
        result = step.run(step_context)

        jhelper.run_action.assert_called_once()
        assert result.result_type == ResultType.COMPLETED

    def test_run_action_failed(self, cclient, jhelper, step_context):
        jhelper.run_action.side_effect = ActionFailedException("Action failed...")

        step = SetCephMgrPoolSizeStep(cclient, jhelper, "test-model")
        result = step.run(step_context)

        jhelper.run_action.assert_called_once()
        expected_message = "Action failed..."
        assert result.result_type == ResultType.FAILED
        assert result.message == expected_message
