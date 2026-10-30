# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Offline wire contracts from HorizonDB 2026-10-01-preview (spec commit 8c2fc31)."""

from datetime import datetime, timezone
from importlib import import_module
from unittest import TestCase
from unittest.mock import Mock, patch, sentinel

from azure.cli.core import get_default_cli
from azure.cli.core.aaz import AAZCommand, AAZPasswordArg
from azure.cli.core.azclierror import InvalidArgumentValueError


class ApiContractTests(TestCase):

    def setUp(self):
        http_client = patch(
            'azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client',
            side_effect=AssertionError('Contract tests must not use Azure credentials or HTTP clients.')
        )
        http_client.start()
        self.addCleanup(http_client.stop)
        self.cli_ctx = get_default_cli()
        self.args = {
            'subscription': '00000000-0000-0000-0000-000000000001',
            'resource_group': 'test-rg',
            'cluster_name': 'test-cluster',
        }
        self.cluster_path = (
            '/subscriptions/00000000-0000-0000-0000-000000000001'
            '/resourceGroups/test-rg/providers/Microsoft.HorizonDb/clusters/test-cluster'
        )

    @staticmethod
    def _command_type(module, name):
        # Exercise the generated request contract directly.
        return getattr(import_module('azext_horizondb.aaz.latest.horizondb.' + module), name)

    @staticmethod
    def _option_args(command_type, values):
        schema = command_type.get_arguments_schema()
        return {
            schema._fields_alias_map[option]: value  # pylint: disable=protected-access
            for option, value in values.items()
        }

    def _operation(self, module, name, operation_name, args=None):
        command_type = self._command_type(module, name)
        command = command_type(cli_ctx=self.cli_ctx)
        arguments = dict(self.args, **(args or {}))
        if module.startswith('cluster._'):
            arguments['name'] = arguments.pop('cluster_name')
        AAZCommand._handler(command, arguments)  # pylint: disable=protected-access
        client = Mock()
        client.format_url.side_effect = lambda template, **params: (
            'https://management.azure.com' + template.format(**params)
        )
        with patch.object(command.ctx, 'get_http_client', return_value=client):
            operation = getattr(command, operation_name)(ctx=command.ctx)
        return command, operation

    def _assert_request(self, operation, method, path):
        self.assertEqual(operation.method, method)
        self.assertEqual(operation.url, 'https://management.azure.com' + path)
        self.assertEqual(operation.query_parameters, {'api-version': '2026-10-01-preview'})

    def _assert_put_201_is_async(self, module, operation_name, args, name='Create'):
        command, operation = self._operation(module, name, operation_name, args)
        path = self.cluster_path
        if module == 'cluster.pool._create':
            path += '/pools/' + args['name']
        self._assert_request(operation, 'PUT', path)
        self.assertTrue(command.AZ_SUPPORT_NO_WAIT)
        session = Mock()
        session.http_response.status_code = 201
        session.http_response.headers = {
            'Azure-AsyncOperation': 'https://management.azure.com/operations/test-operation',
            'Retry-After': '5',
        }
        operation.client.send_request.return_value = session
        operation.client.build_lro_polling.return_value = sentinel.polling
        with patch.object(operation, 'make_request', return_value=sentinel.request):
            self.assertIs(operation(), sentinel.polling)
        operation.client.send_request.assert_called_once_with(request=sentinel.request, stream=False)
        operation.client.build_lro_polling.assert_called_once()
        call = operation.client.build_lro_polling.call_args
        self.assertIs(call.args[1], session)
        self.assertFalse(call.args[0])
        self.assertEqual(call.kwargs['lro_options']['final-state-via'], 'azure-async-operation')
        self.assertEqual(call.kwargs['path_format_arguments'], operation.url_parameters)

    def test_cluster_put_201_uses_azure_async_operation(self):
        self._assert_put_201_is_async(
            'cluster._create', 'ClustersCreateOrReplace', {'location': 'eastus2', 'postgresql_version': '17'})

    def test_restore_put_201_uses_azure_async_operation(self):
        self._assert_put_201_is_async('cluster._restore', 'ClustersCreateOrReplace', {
            'location': 'eastus2', 'creation_source_cluster': self.cluster_path,
            'point_in_time': '2026-10-01T10:30:00Z',
        }, name='Restore')

    def test_pool_put_201_uses_azure_async_operation(self):
        self._assert_put_201_is_async('cluster.pool._create', 'PoolsCreateOrReplace', {'name': 'test-pool'})

    def test_pool_is_a_proxy_resource_without_tags(self):
        for module, name in [('cluster.pool._create', 'Create'), ('cluster.pool._update', 'Update')]:
            with self.subTest(command=module):
                command_type = self._command_type(module, name)
                schema = command_type.get_arguments_schema()
                self.assertNotIn('tags', schema._fields)  # pylint: disable=protected-access
                self.assertNotIn('--tags', schema._fields_alias_map)  # pylint: disable=protected-access
        _, operation = self._operation(
            'cluster.pool._create', 'Create', 'PoolsCreateOrReplace', {
                'name': 'test-pool',
                'compute_generation': 1,
                'compute_processor': 'Intel',
                'v_cores': 2,
                'node_count': 1,
                'high_availability_mode': 'Disabled',
            }
        )
        body = operation.content
        self.assertEqual(body['properties']['nodeCount'], 1)
        self.assertNotIn('tags', body)

    def test_point_in_time_restore_fields_reach_cluster_put_body(self):
        command_type = self._command_type('cluster._restore', 'Restore')
        source_id = self.cluster_path.replace('test-cluster', 'source-cluster')
        restore_args = self._option_args(command_type, {
            '--point-in-time': '2026-10-01T10:30:00Z',
            '--creation-source-cluster': source_id,
            '--creation-source-cluster-location': 'eastus2',
        })
        _, operation = self._operation(
            'cluster._restore', 'Restore', 'ClustersCreateOrReplace',
            dict(restore_args, location='westus3')
        )
        self._assert_request(operation, 'PUT', self.cluster_path)
        body = operation.content
        self.assertEqual(body['location'], 'westus3')
        properties = body['properties']
        self.assertEqual(properties['creationMode'], 'PointInTimeRestore')
        self.assertEqual(
            datetime.fromisoformat(properties['pointInTimeUtc'].replace('Z', '+00:00')),
            datetime(2026, 10, 1, 10, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(properties['creationSourceClusterResourceId'], source_id)
        self.assertEqual(properties['creationSourceClusterLocation'], 'eastus2')
        self.assertNotIn('postgreSqlVersion', properties)
        for name in ('creationMode', 'pointInTimeUtc', 'creationSourceClusterResourceId',
                     'creationSourceClusterLocation'):
            self.assertNotIn(name, body)

    def test_cluster_command_schemas_are_specific_to_the_creation_mode(self):
        for module, name, required, excluded in (
                ('cluster._create', 'Create', {'postgresql_version'}, {
                    'creation_mode', 'creation_source_cluster',
                    'creation_source_cluster_location', 'point_in_time'}),
                ('cluster._restore', 'Restore', {'creation_source_cluster', 'point_in_time'}, {
                    'creation_mode', 'postgresql_version'})):
            schema = self._command_type(module, name).get_arguments_schema()
            for field in required:
                with self.subTest(command=name, required=field):
                    self.assertTrue(schema._fields[field]._required)
            for field in excluded:
                with self.subTest(command=name, excluded=field):
                    self.assertNotIn(field, schema._fields)

    def test_create_always_sends_create_mode_without_restore_properties(self):
        _, operation = self._operation('cluster._create', 'Create', 'ClustersCreateOrReplace', {
            'location': 'eastus2', 'postgresql_version': '17',
        })
        self.assertEqual('Create', operation.content['properties']['creationMode'])
        self.assertEqual('17', operation.content['properties']['postgreSqlVersion'])
        for property_name in ('creationSourceClusterLocation', 'creationSourceClusterResourceId', 'pointInTimeUtc'):
            self.assertNotIn(property_name, operation.content['properties'])

    def test_firewall_create_name_and_ipv4_schema_constraints(self):
        command_type = self._command_type('cluster.pool.firewall_rule._create', 'Create')
        schema = command_type.get_arguments_schema()
        # AAZ preserves regex metadata but does not enforce regexes in format_args.
        name_format = schema.name._fmt  # pylint: disable=protected-access
        self.assertEqual(name_format._min_length, 1)  # pylint: disable=protected-access
        self.assertEqual(name_format._max_length, 80)  # pylint: disable=protected-access
        for name in ('a', 'Allow_Office.1-rule_', 'a' * 80):
            with self.subTest(valid_name=name):
                self.assertRegex(name, name_format._pattern)  # pylint: disable=protected-access
        for name in ('', '_rule', 'rule.', 'rule-', 'rule/name', 'a' * 81):
            with self.subTest(invalid_name=name):
                self.assertNotRegex(name, name_format._pattern)  # pylint: disable=protected-access
        for field in (schema.start_ip_address, schema.end_ip_address):
            pattern = field._fmt._pattern  # pylint: disable=protected-access
            for address in ('0.0.0.0', '10.20.30.40', '255.255.255.255'):
                with self.subTest(valid_address=address):
                    self.assertRegex(address, pattern)
            for address in ('256.1.1.1', '1.2.3', '1.2.3.4.5', '-1.0.0.0', '01.2.3.4', '::1'):
                with self.subTest(invalid_address=address):
                    self.assertNotRegex(address, pattern)

    def test_firewall_create_put_body_and_required_range_endpoints(self):
        args = {
            'pool_name': 'test-pool', 'name': 'Office_1',
            'start_ip_address': '10.0.0.1', 'end_ip_address': '10.0.0.255',
            'description': 'Office range',
        }
        _, operation = self._operation(
            'cluster.pool.firewall_rule._create', 'Create', 'FirewallRulesCreateOrReplace', args
        )
        self._assert_request(operation, 'PUT', self.cluster_path + '/pools/test-pool/firewallRules/Office_1')
        with patch.object(operation, 'serialize_content', wraps=operation.serialize_content) as serialize:
            body = operation.content
        self.assertEqual(body, {
            'properties': {
                'startIpAddress': '10.0.0.1',
                'endIpAddress': '10.0.0.255',
                'description': 'Office range',
            },
        })
        properties_schema = serialize.call_args.args[0]._schema.properties  # pylint: disable=protected-access
        for field in ('startIpAddress', 'endIpAddress'):
            with self.subTest(required_field=field):
                self.assertTrue(getattr(properties_schema, field)._flags['required'])  # pylint: disable=protected-access

    def test_firewall_create_rejects_overlong_name_and_description(self):
        for changes in ({'name': 'a' * 81}, {'description': 'd' * 1025}):
            with self.subTest(changes=changes):
                with self.assertRaises(InvalidArgumentValueError):
                    self._operation(
                        'cluster.pool.firewall_rule._create', 'Create', 'FirewallRulesCreateOrReplace',
                        dict({'pool_name': 'test-pool', 'name': 'office',
                              'start_ip_address': '0.0.0.0', 'end_ip_address': '255.255.255.255'}, **changes)
                    )

    def test_cluster_failover_posts_to_action_url(self):
        command, operation = self._operation('cluster._failover', 'Failover', 'ClustersFailover')
        self._assert_request(operation, 'POST', self.cluster_path + '/failover')
        self.assertTrue(command.AZ_SUPPORT_NO_WAIT)
        self.assertIsNone(operation.content)

    def test_pool_lifecycle_actions_post_to_action_urls(self):
        for action in ('start', 'stop', 'restart'):
            with self.subTest(action=action):
                command, operation = self._operation(
                    'cluster.pool._' + action, action.title(), 'Pools' + action.title(),
                    {'name': 'test-pool'}
                )
                self._assert_request(operation, 'POST', self.cluster_path + '/pools/test-pool/' + action)
                self.assertTrue(command.AZ_SUPPORT_NO_WAIT)
                self.assertIsNone(operation.content)

    def test_cdc_activate_identity_sends_etag_header_and_action_body(self):
        module = 'cluster.change_data_capture_destination._activate_identity'
        command_type = self._command_type(module, 'ActivateIdentity')
        assignment_id = self.cluster_path + '/changeDataCaptureDestinations/test-destination/identityAssignments/next'
        args = self._option_args(command_type, {
            '--name': 'test-destination',
            '--if-match': '"destination-etag"',
            '--identity-assignment': assignment_id,
            '--drain-existing-sessions': True,
        })
        command, operation = self._operation(
            module, 'ActivateIdentity', 'ChangeDataCaptureDestinationsActivateIdentity', args
        )
        self._assert_request(
            operation, 'POST', self.cluster_path + '/changeDataCaptureDestinations/test-destination/activateIdentity'
        )
        self.assertTrue(command.AZ_SUPPORT_NO_WAIT)
        self.assertEqual(operation.header_parameters['If-Match'], '"destination-etag"')
        self.assertNotIn('If-Match', operation.query_parameters)
        self.assertEqual(operation.content, {
            'identityAssignmentResourceId': assignment_id, 'drainExistingSessions': True,
        })
        schema = command_type.get_arguments_schema()
        match_arg = schema._fields[schema._fields_alias_map['--if-match']]  # pylint: disable=protected-access
        self.assertTrue(match_arg._required)  # pylint: disable=protected-access

    def test_password_credentials_have_secret_logging_flags(self):
        module = 'cluster.authentication.password._create'
        command_type = self._command_type(module, 'Create')
        values = {
            '--state': 'Enabled',
            '--administrator-login': 'testadmin',
            '--administrator-login-password': 'UnitTest-NotARealPassword-123!',
        }
        args = self._option_args(command_type, values)
        _, operation = self._operation(module, 'Create', 'PasswordAuthenticationsCreateOrReplace', args)
        self._assert_request(operation, 'PUT', self.cluster_path + '/authentications/passwordMethod')
        with patch.object(operation, 'serialize_content', wraps=operation.serialize_content) as serialize:
            body = operation.content
        self.assertEqual(body, {'properties': {
            'state': 'Enabled', 'administratorLogin': values['--administrator-login'],
            'administratorLoginPassword': values['--administrator-login-password'],
        }})
        content_value = serialize.call_args.args[0]
        properties_schema = content_value._schema.properties  # pylint: disable=protected-access
        schema = command_type.get_arguments_schema()
        for option, property_name in (
                ('--administrator-login', 'administratorLogin'),
                ('--administrator-login-password', 'administratorLoginPassword')):
            with self.subTest(credential=property_name):
                arg = schema._fields[schema._fields_alias_map[option]]  # pylint: disable=protected-access
                self.assertIsInstance(arg, AAZPasswordArg)
                field = getattr(properties_schema, property_name)
                self.assertTrue(field._flags.get('secret'))  # pylint: disable=protected-access
