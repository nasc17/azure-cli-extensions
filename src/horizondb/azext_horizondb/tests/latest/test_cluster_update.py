# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest import TestCase
from unittest.mock import patch

from azure.cli.core import get_default_cli
from azure.cli.core.aaz import AAZCommand
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_horizondb._cluster import ClusterUpdate


class ClusterUpdateTests(TestCase):
    def setUp(self):
        self.cli_ctx = get_default_cli()
        self.args = {
            'subscription': '00000000-0000-0000-0000-000000000001',
            'resource_group': 'example-rg',
            'name': 'example-cluster',
        }
        self.identity = (
            '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/example-rg'
            '/providers/Microsoft.ManagedIdentity/userAssignedIdentities/example-identity'
        )
        http_client = patch(
            'azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client',
            side_effect=AssertionError('Unit tests must not use Azure credentials or HTTP clients.'),
        )
        http_client.start()
        self.addCleanup(http_client.stop)

    def _content(self, **args):
        command = ClusterUpdate(cli_ctx=self.cli_ctx)
        AAZCommand._handler(command, dict(self.args, **args))  # pylint: disable=protected-access
        command.pre_operations()
        with patch.object(command.ctx, 'get_http_client'):
            operation = command.ClustersUpdate(ctx=command.ctx)
        self.assertEqual('PATCH', operation.method)
        return operation.content

    def test_removal_example_sends_explicit_null_without_replacing_other_identities(self):
        self.assertEqual({
            'identity': {'type': 'UserAssigned', 'userAssignedIdentities': {self.identity: None}},
        }, self._content(remove_user_assigned_identities=[self.identity]))

    def test_unrelated_updates_do_not_add_an_identity_patch(self):
        self.assertEqual({'properties': {'aiModelManagement': 'Enabled'}},
                         self._content(ai_model_management='Enabled'))

    def test_add_and_remove_different_identities_in_one_patch(self):
        addition = self.identity + '-new'
        self.assertEqual({
            'identity': {'type': 'UserAssigned',
                         'userAssignedIdentities': {self.identity: None, addition: {}}},
        }, self._content(mi_user_assigned=[addition], remove_user_assigned_identities=[self.identity]))

    def test_invalid_or_conflicting_identity_rejected_before_http(self):
        for args in (
                {'remove_user_assigned_identities': ['/subscriptions/sub/providers/Microsoft.HorizonDb/clusters/c']},
                {'remove_user_assigned_identities': [self.identity.upper()], 'mi_user_assigned': [self.identity]}):
            with self.subTest(arguments=args):
                command = ClusterUpdate(cli_ctx=self.cli_ctx)
                with patch.object(command, 'ClustersUpdate') as operation:
                    with self.assertRaises(InvalidArgumentValueError):
                        command(command_args=dict(self.args, **args)).result()
                operation.assert_not_called()
