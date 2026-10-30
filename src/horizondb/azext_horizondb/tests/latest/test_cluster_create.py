# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest import TestCase
from unittest.mock import Mock, patch

from azure.core.exceptions import HttpResponseError
from azure.cli.core import get_default_cli
from azure.cli.core.aaz import AAZCommand

from azext_horizondb import HorizonDBCommandsLoader
from azext_horizondb.aaz.latest.horizondb.cluster import Create, Restore
from azext_horizondb._pool import PoolCreate, PoolUpdate


class ClusterCreateTests(TestCase):

    def setUp(self):
        self.loader = HorizonDBCommandsLoader(cli_ctx=get_default_cli())
        self.commands = self.loader.load_command_table(None)
        self.command = self.commands['horizondb cluster create']
        self.args = {
            'subscription': '00000000-0000-0000-0000-000000000001',
            'resource_group': 'test-rg',
            'name': 'test-cluster',
            'location': 'japaneast',
            'postgresql_version': '17',
        }
        self.cluster = {'name': 'test-cluster', 'location': 'japaneast'}
        http_client = patch(
            'azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client',
            side_effect=AssertionError('Unit tests must not use Azure credentials or HTTP clients.'),
        )
        http_client.start()
        self.addCleanup(http_client.stop)

    def test_loader_uses_generated_cluster_create_and_preserves_pool_commands(self):
        self.assertIsInstance(self.command, Create)
        self.assertIsInstance(self.commands['horizondb cluster restore'], Restore)
        self.assertIsInstance(self.commands['horizondb cluster pool create'], PoolCreate)
        self.assertIsInstance(self.commands['horizondb cluster pool update'], PoolUpdate)
        self.assertIs(type(self.command)._handler, Create._handler)
        self.assertIs(type(self.command).post_operations, Create.post_operations)

    def test_schema_contains_only_generated_cluster_arguments(self):
        self.command.load_arguments()
        self.assertEqual(
            set(Create.get_arguments_schema()._fields),
            set(self.command.get_arguments_schema()._fields),
        )
        self.assertEqual(
            {'name', 'resource_group', 'location', 'postgresql_version'},
            {name for name, argument in self.command.get_arguments_schema()._fields.items() if argument._required},
        )
        for name in ('pool_name', 'compute_generation', 'compute_processor', 'v_cores',
                     'node_count', 'high_availability_mode', 'authentication', 'administrator_login_password'):
            with self.subTest(argument=name):
                self.assertNotIn(name, self.command.arguments)

    def test_cluster_create_exposes_no_wait(self):
        self.command.load_arguments()
        self.assertTrue(self.command.AZ_SUPPORT_NO_WAIT)
        self.assertEqual(['--no-wait'], self.command.arguments['no_wait'].type.settings['options_list'])

    def test_creation_commands_send_only_one_cluster_put_and_return_cluster(self):
        restore_args = {key: value for key, value in self.args.items() if key != 'postgresql_version'}
        restore_args.update(
            creation_source_cluster=(
                '/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test-rg/'
                'providers/Microsoft.HorizonDb/clusters/source'
            ),
            point_in_time='2026-10-01T12:00:00Z',
        )
        for verb, mode, arguments in (
                ('create', 'Create', self.args), ('restore', 'PointInTimeRestore', restore_args)):
            command = self.commands['horizondb cluster ' + verb]
            for status_code in (200, 201, 202):
                for no_wait in (False, True):
                    with self.subTest(command=verb, status=status_code, no_wait=no_wait):
                        client = Mock()
                        client.format_url.side_effect = lambda template, **values: template.format(**values)
                        client.send_request.return_value.http_response.status_code = status_code
                        schema_builder = command.ClustersCreateOrReplace._build_schema_on_200_201
                        client.build_lro_polling.return_value.run.side_effect = lambda: command.ctx.set_var(
                            'instance', self.cluster, schema_builder=schema_builder,
                        )
                        with patch(
                                'azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client',
                                return_value=client):
                            result = command(command_args=dict(arguments, no_wait=no_wait))
                            if not no_wait:
                                result = result.result()
                        self.assertEqual(None if no_wait else self.cluster, result)
                        client._request.assert_called_once()  # pylint: disable=protected-access
                        request = client._request.call_args.args  # pylint: disable=protected-access
                        self.assertEqual(request[0], 'PUT')
                        self.assertEqual(request[1], (
                            '/subscriptions/00000000-0000-0000-0000-000000000001'
                            '/resourceGroups/test-rg/providers/Microsoft.HorizonDb/clusters/test-cluster'
                        ))
                        self.assertEqual(request[2], {'api-version': '2026-10-01-preview'})
                        properties = request[4]['properties']
                        self.assertEqual(properties['creationMode'], mode)
                        if verb == 'create':
                            self.assertEqual(properties['postgreSqlVersion'], '17')
                        else:
                            self.assertNotIn('postgreSqlVersion', properties)
                            self.assertEqual(properties['creationSourceClusterResourceId'],
                                             restore_args['creation_source_cluster'])
                        self.assertEqual(bool(client.build_lro_polling.call_args.args[0]), no_wait)

    def test_cluster_request_contains_only_cluster_settings(self):
        args = dict(self.args, backup_retention_days=7, geo_redundancy='Enabled', public_access='Disabled')
        AAZCommand._handler(self.command, args)  # pylint: disable=protected-access
        with patch.object(self.command.ctx, 'get_http_client'):
            operation = self.command.ClustersCreateOrReplace(ctx=self.command.ctx)
        self.assertEqual(operation.content, {
            'location': 'japaneast',
            'properties': {
                'creationMode': 'Create',
                'postgreSqlVersion': '17',
                'backup': {'retentionDays': 7, 'geoRedundancy': 'Enabled'},
                'network': {'publicAccess': 'Disabled'},
            },
        })

    def test_cluster_polling_failure_is_reported_without_other_resource_requests(self):
        client = Mock()
        client.format_url.side_effect = lambda template, **values: template.format(**values)
        client.send_request.return_value.http_response.status_code = 202
        client.build_lro_polling.return_value.run.side_effect = HttpResponseError('Cluster async operation failed')
        with patch(
                'azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client',
                return_value=client):
            with self.assertRaisesRegex(HttpResponseError, 'Cluster async operation failed'):
                self.command(command_args=self.args).result()
        client._request.assert_called_once()  # pylint: disable=protected-access

    def test_cluster_name_defaultpool_has_no_pool_name_collision(self):
        with patch.object(self.command, 'ClustersCreateOrReplace') as create, \
                patch.object(self.command, '_output', return_value=self.cluster):
            self.command(command_args=dict(self.args, name='defaultpool')).result()
        create.assert_called_once()
