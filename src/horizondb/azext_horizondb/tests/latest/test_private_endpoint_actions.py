# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from azure.cli.core import get_default_cli
from azure.cli.core.aaz import AAZCommand

from azext_horizondb.aaz.latest.horizondb.cluster.private_endpoint_connection._approve import Approve
from azext_horizondb.aaz.latest.horizondb.cluster.private_endpoint_connection._reject import Reject


class PrivateEndpointActionTests(TestCase):

    def test_generation_clones_actions_before_removing_redundant_leaves(self):
        # Isolate the generator's workspace policy without requiring aaz-dev,
        # Swagger checkouts, or writing generated files in this offline suite.
        path = Path(__file__).parents[3] / 'dev' / 'generate.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'configure_private_endpoint_actions')
        set_constant = Mock()
        namespace = {'CMDCommand': deepcopy, 'set_constant': set_constant}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
        prefix = ['horizondb', 'cluster', 'private-endpoint-connection']
        state = SimpleNamespace(options=['private-link-service-connection-state'], var='$resource.properties.state')
        original = Mock()
        original.to_native.return_value = SimpleNamespace(arg_groups=[SimpleNamespace(args=[state])])
        commands = {'create': original, 'update': Mock(), 'show': Mock(), 'list': Mock(), 'delete': Mock()}
        preserved = {name: commands[name] for name in ('show', 'list', 'delete')}
        editor = Mock()
        editor.find_command.side_effect = lambda *names: commands[names[-1]]

        def add(*names, command):
            self.assertIn('create', commands)
            commands[names[-1]] = command

        def remove(*names):
            self.assertIn('approve', commands)
            self.assertIn('reject', commands)
            commands.pop(names[-1])

        editor._add_command.side_effect = add
        editor._remove_command.side_effect = remove
        workspace = Mock()
        workspace.find_command_tree_leaf.return_value = SimpleNamespace(names=prefix + ['create'])
        workspace.load_cfg_editor_by_command.return_value = editor
        namespace['configure_private_endpoint_actions'](workspace)

        self.assertEqual({'approve', 'reject', 'show', 'list', 'delete'}, set(commands))
        for name, command in preserved.items():
            self.assertIs(command, commands[name])
        self.assertIsNot(commands['approve'], commands['reject'])
        for action, status in (('approve', 'Approved'), ('reject', 'Rejected')):
            self.assertEqual(action, commands[action].name)
            set_constant.assert_any_call(editor, commands[action], state.var + '.status', status)
            editor.flatten_arg.assert_any_call(*prefix, action, arg_var=state.var)
        self.assertEqual(2, set_constant.call_count)
        self.assertEqual([call(*prefix, 'create'), call(*prefix, 'update')], editor._remove_command.call_args_list)
        workspace._unset_cfg_editor.assert_called_once_with(editor)
        workspace._set_cfg_editor.assert_called_once_with(editor)
        editor.reformat.assert_called_once_with()

    def test_generated_approval_and_rejection_put_the_selected_status(self):
        for command_type, status in ((Approve, 'Approved'), (Reject, 'Rejected')):
            with self.subTest(status=status):
                command = command_type(cli_ctx=get_default_cli())
                command.load_arguments()
                self.assertNotIn('status', command.arguments)
                self.assertIn('no_wait', command.arguments)
                AAZCommand._handler(command, {
                    'subscription': '00000000-0000-0000-0000-000000000001',
                    'resource_group': 'test-rg',
                    'cluster_name': 'test-cluster',
                    'name': 'test-connection',
                    'description': 'Reviewed connection',
                })
                with patch.object(command.ctx, 'get_http_client'):
                    operation = command.PrivateEndpointConnectionsApproveOrReject(ctx=command.ctx)
                self.assertEqual(operation.method, 'PUT')
                self.assertEqual(operation.content, {
                    'properties': {
                        'privateLinkServiceConnectionState': {
                            'status': status, 'description': 'Reviewed connection',
                        },
                    },
                })
