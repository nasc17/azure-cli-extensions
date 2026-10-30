# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Offline orchestration tests; generated HTTP contracts are tested separately."""

from copy import deepcopy
from argparse import SUPPRESS
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from azure.cli.core import get_default_cli
from azure.cli.core.aaz import AAZCommand
from azure.cli.core.parser import AzCliCommandParser
from azure.cli.core.azclierror import (
    AzureResponseError, CLIInternalError, InvalidArgumentValueError, RequiredArgumentMissingError,
)
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from azext_horizondb import _create as workflow
from azext_horizondb.tests.latest import load_commands


SUBSCRIPTION = '11111111-1111-1111-1111-111111111111'
DEFAULT_ID = (f'/subscriptions/{SUBSCRIPTION}/providers/Microsoft.HorizonDb/'
              'locations/eastus2/parameterGroups/pg17')
SOURCE_ID = (f'/subscriptions/{SUBSCRIPTION}/resourceGroups/source-rg/'
             'providers/Microsoft.HorizonDb/clusters/source')
IDENTITY_ID = (f'/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/'
               'providers/Microsoft.ManagedIdentity/userAssignedIdentities/key')
CAPABILITIES = [{
    'properties': {
        'clusterCapabilities': {'supportedPostgreSqlVersions': [{'name': '17'}]},
        'poolCapabilities': {'supportedProcessors': [
            {'name': 'Intel', 'supportedGenerations': [
                {'computeGeneration': 1, 'supportedComputeModels': [
                    {'type': 'Provisioned', 'supportedComputeSizes': [{'vCores': 16}, {'vCores': 4}]}]}]},
            {'name': 'AMD', 'supportedGenerations': [
                {'computeGeneration': 2, 'supportedComputeModels': [
                    {'type': 'Provisioned', 'supportedComputeSizes': [{'vCores': 1}]}]},
                {'computeGeneration': 1, 'supportedComputeModels': [
                    {'type': 'Provisioned', 'supportedComputeSizes': [{'vCores': 8}, {'vCores': 2}]}]}]}
        ]}
    }
}]


class Executor:
    def __init__(self):
        self.calls = []
        self.created = False
        self.existing = False
        self.raced = False
        self.show_count = 0
        self.states = {}
        self.ai = None
        self.fail_command = None
        self.catalog = deepcopy(CAPABILITIES)
        self.defaults = [{'id': DEFAULT_ID, 'properties': {'postgreSqlVersion': '17'}}]
        self.default_version = '17'
        self.endpoints = [{'id': 'endpoint', 'properties': {
            'scope': 'Cluster', 'role': 'ReadWrite', 'fullyQualifiedDomainName': 'cluster.example.test'}}]

    @property
    def writes(self):
        return [(name, arguments) for name, arguments in self.calls if name.endswith((' create', ' restore', ' update'))]

    def resource_group(self, name):
        self.calls.append(('group show', {'name': name}))
        return {'location': 'East US 2'}

    def capabilities(self, location):
        self.calls.append(('capabilities list', {'location': location}))
        return self.catalog

    def run(self, command, **arguments):
        self.calls.append((command, arguments))
        if command == self.fail_command:
            raise HttpResponseError('simulated service failure')
        if command == 'horizondb cluster show':
            if arguments.get('name') == 'source':
                return {'location': 'eastus2', 'properties': {'postgreSqlVersion': '17'}}
            self.show_count += 1
            if self.existing or self.created or (self.raced and self.show_count == 2):
                return {'id': 'cluster', 'location': 'eastus2',
                        'properties': {'aiModelManagement': self.ai, 'postgreSqlVersion': '17'}}
            raise ResourceNotFoundError('not found')
        if command == 'horizondb default-parameter-group list':
            return self.defaults
        if command == 'horizondb default-parameter-group show':
            return {'properties': {'postgreSqlVersion': self.default_version}}
        if command in ('horizondb cluster create', 'horizondb cluster restore'):
            self.created = True
            return {'id': 'cluster'}
        if command == 'horizondb cluster pool create':
            return {'id': 'pool', 'properties': {'computeModel': {'vCores': arguments['v_cores']}}}
        if ' authentication ' in command:
            kind = command.split()[-2]
            if command.endswith('create'):
                self.states[kind] = arguments['state']
            return {'properties': {'state': self.states.get(kind),
                                   'administratorLoginPassword': 'must-never-be-output'}}
        if command == 'horizondb cluster update':
            self.ai = arguments['ai_model_management']
            return {'id': 'cluster'}
        if command == 'horizondb cluster endpoint list':
            return self.endpoints
        return {'id': 'child'}


def create(executor, **kwargs):
    arguments = dict(resource_group_name='rg', cluster_name='example', authentication='Password',
                     administrator_login_password='test-Password123!', public_access=['203.0.113.8'])
    arguments.update(kwargs)
    return workflow.horizondb_create(SimpleNamespace(cli_ctx=object()), executor=executor, **arguments)


def call(executor, command):
    return next(arguments for name, arguments in executor.calls if name == command)


class CreateWorkflowTests(TestCase):

    def setUp(self):
        self.executor = Executor()

    def test_smallest_generation_one_default_and_no_secrets(self):
        result = create(self.executor)
        pool = call(self.executor, 'horizondb cluster pool create')
        self.assertEqual(pool['v_cores'], 2)
        self.assertEqual(pool['compute_processor'], 'AMD')
        self.assertEqual(pool['compute_generation'], 1)
        self.assertEqual(pool['name'], 'example-pool')
        self.assertEqual(pool['parameter_group'], DEFAULT_ID)
        self.assertEqual(pool['parameter_apply_method'], 'Immediate')
        self.assertNotIn('scheduled_maintenance', pool)
        cluster = call(self.executor, 'horizondb cluster create')
        self.assertEqual(cluster['location'], 'eastus2')
        self.assertEqual(cluster['postgresql_version'], '17')
        self.assertEqual(cluster['public_access'], 'Enabled')
        self.assertNotIn('tags', cluster)
        self.assertEqual(result['aiModelManagement'], 'Disabled')
        self.assertEqual(result['connection']['sslMode'], 'require')
        self.assertNotIn('test-Password123!', repr(result))
        self.assertNotIn('must-never-be-output', repr(result))
        self.assertNotIn('administratorLogin', repr(result))
        self.assertEqual(self.executor.show_count, 3)
        self.assertLess(
            self.executor.calls.index(('group show', {'name': 'rg'})),
            self.executor.calls.index(('horizondb cluster create', cluster)),
        )

    def test_explicit_processor_and_cores_respected(self):
        create(self.executor, compute_processor='Intel', v_cores=4)
        pool = call(self.executor, 'horizondb cluster pool create')
        self.assertEqual((pool['compute_processor'], pool['v_cores']), ('Intel', 4))

    def test_create_only_checks_before_any_write(self):
        for raced in (False, True):
            with self.subTest(raced=raced):
                executor = Executor()
                executor.existing = not raced
                executor.raced = raced
                with self.assertRaisesRegex(InvalidArgumentValueError, 'create-only'):
                    create(executor)
                self.assertEqual(executor.writes, [])

    def test_non_404_target_failure_is_not_treated_as_missing(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                executor = Executor()
                response = SimpleNamespace(status_code=status, reason='error', headers={})
                original = executor.run

                def run(command, **arguments):
                    if command == 'horizondb cluster show':
                        raise HttpResponseError(response=response)
                    return original(command, **arguments)

                executor.run = run
                with self.assertRaises(HttpResponseError):
                    create(executor)
                self.assertEqual(executor.writes, [])

    def test_generic_http_404_is_accepted(self):
        original = self.executor.run

        def run(command, **arguments):
            try:
                return original(command, **arguments)
            except ResourceNotFoundError as ex:
                raise HttpResponseError(response=SimpleNamespace(
                    status_code=404, reason='Not Found', headers={})) from ex

        self.executor.run = run
        create(self.executor)
        self.assertTrue(self.executor.created)

    def test_bad_prerequisites_never_write(self):
        for name, mutate in (
                ('no capabilities', lambda executor: setattr(executor, 'catalog', [])),
                ('no default', lambda executor: setattr(executor, 'defaults', [])),
                ('ambiguous default', lambda executor: setattr(executor, 'defaults', executor.defaults * 2)),
                ('wrong version', lambda executor: setattr(executor, 'default_version', '18')),
                ('wrong location', lambda executor: executor.defaults[0].update(
                    id=DEFAULT_ID.replace('eastus2', 'westus')))):
            with self.subTest(prerequisite=name):
                executor = Executor()
                mutate(executor)
                with self.assertRaises((InvalidArgumentValueError, AzureResponseError)):
                    create(executor)
                self.assertEqual(executor.writes, [])

    def test_resource_group_must_exist_even_with_explicit_location(self):
        with patch.object(self.executor, 'resource_group', side_effect=ResourceNotFoundError('missing group')):
            with self.assertRaises(ResourceNotFoundError):
                create(self.executor, location='eastus2')
        self.assertEqual(self.executor.writes, [])

    def test_invalid_public_access_is_preflight_error(self):
        for access in ([], ['::1'], ['0.0.0.0'], ['203.0.113.9-203.0.113.8'], ['invalid']):
            with self.subTest(access=access):
                executor = Executor()
                with self.assertRaises(InvalidArgumentValueError):
                    create(executor, public_access=access)
                self.assertEqual(executor.writes, [])

    def test_public_access_normalization_and_deduplication(self):
        self.assertEqual(
            workflow._public_ranges(['203.0.113.8', '203.0.113.8/32', '203.0.113.16/30']),
            [('203.0.113.16', '203.0.113.19'), ('203.0.113.8', '203.0.113.8')],
        )

    def test_caller_ipv4_default_does_not_prompt_for_all_addresses(self):
        path = 'azure.cli.command_modules.rdbms.flexible_server_virtual_network.prepare_public_network'
        with patch(path, return_value=('203.0.113.8', '203.0.113.8')) as discovery:
            self.assertEqual(workflow._public_ranges(None), [('203.0.113.8', '203.0.113.8')])
        discovery.assert_called_once_with(None, yes=True)

    def test_authentication_states_and_order(self):
        for authentication in ('Entra', 'Both', 'Password'):
            with self.subTest(authentication=authentication):
                executor = Executor()
                administrator = None if authentication == 'Password' else {
                    'object_id': SUBSCRIPTION, 'principal_name': 'admin',
                    'principal_type': 'User', 'tenant_id': SUBSCRIPTION,
                }
                with patch.object(workflow, '_administrator', return_value=administrator):
                    result = create(
                        executor, authentication=authentication,
                        administrator_login_password=None if authentication == 'Entra' else 'test-Password123!',
                    )
                self.assertEqual(executor.states['password'], 'Disabled' if authentication == 'Entra' else 'Enabled')
                self.assertEqual(
                    executor.states['microsoft-entra'], 'Disabled' if authentication == 'Password' else 'Enabled',
                )
                writes = [name for name, _ in executor.writes]
                password_index = writes.index('horizondb cluster authentication password create')
                entra_index = writes.index('horizondb cluster authentication microsoft-entra create')
                self.assertEqual(password_index < entra_index, authentication != 'Entra')
                self.assertEqual(result['connection']['authentication'], authentication)

    def test_entra_rejects_password_before_writes(self):
        with patch.object(workflow, '_administrator', return_value={}):
            with self.assertRaisesRegex(InvalidArgumentValueError, 'Password credentials'):
                create(self.executor, authentication='Entra')
        self.assertEqual(self.executor.writes, [])

    def test_authentication_verification_failure_stops_firewall_and_ai(self):
        original = self.executor.run

        def run(command, **arguments):
            if command == 'horizondb cluster authentication password show':
                return {'state': 'Disabled'}
            return original(command, **arguments)

        self.executor.run = run
        with self.assertRaisesRegex(AzureResponseError, 'authentication state'):
            create(self.executor)
        self.assertTrue(self.executor.created)
        self.assertFalse(any(
            'firewall-rule' in name or name.endswith(' update') for name, _ in self.executor.writes
        ))

    def test_ai_is_opt_in_and_verified(self):
        result = create(self.executor, enable_ai=True)
        self.assertEqual(result['aiModelManagement'], 'Enabled')
        self.assertEqual(call(self.executor, 'horizondb cluster update')['ai_model_management'], 'Enabled')

    def test_ai_state_mismatch_and_missing_endpoint_fail_without_cleanup(self):
        for mismatch in ('ai', 'endpoint'):
            with self.subTest(mismatch=mismatch):
                executor = Executor()
                if mismatch == 'endpoint':
                    executor.endpoints = []
                original = executor.run

                def run(command, **arguments):
                    result = original(command, **arguments)
                    if mismatch == 'ai' and command == 'horizondb cluster update':
                        executor.ai = 'Enabled'
                    return result

                executor.run = run
                with self.assertRaises(AzureResponseError):
                    create(executor)
                self.assertTrue(executor.created)
                self.assertFalse(any(name.endswith(' delete') for name, _ in executor.calls))

    def test_partial_failure_retains_created_resources(self):
        for command in (
                'horizondb cluster pool create',
                'horizondb cluster authentication password create',
                'horizondb cluster pool firewall-rule create',
                'horizondb cluster update'):
            with self.subTest(command=command):
                executor = Executor()
                executor.fail_command = command
                with self.assertLogs(workflow.logger, level='ERROR') as logs:
                    with self.assertRaises(HttpResponseError):
                        create(executor)
                self.assertTrue(executor.created)
                self.assertFalse(any(name.endswith(' delete') for name, _ in executor.calls))
                self.assertIn('retained for manual recovery', '\n'.join(logs.output))
                self.assertNotIn('test-Password123!', '\n'.join(logs.output))

    def test_invalid_restore_encryption_and_topology_never_write(self):
        for options in (
                {'data_encryption_type': 'AzureKeyVault'},
                {'primary_encryption_key_uri': 'https://vault.vault.azure.net/keys/key'},
                {'data_encryption_type': 'AzureKeyVault', 'primary_encryption_key_uri': 'https://vault/keys/key',
                 'primary_encryption_identity': IDENTITY_ID},
                {'data_encryption_type': 'AzureKeyVault', 'primary_encryption_key_uri': 'https://vault/keys/key/version',
                 'primary_encryption_identity': IDENTITY_ID, 'user_assigned_identities': [IDENTITY_ID]},
                {'data_encryption_type': 'AzureKeyVault', 'primary_encryption_key_uri': 'https://vault/keys/key',
                 'primary_encryption_identity': IDENTITY_ID, 'user_assigned_identities': [IDENTITY_ID],
                 'geo_redundancy': 'Enabled'},
                {'creation_mode': 'PointInTimeRestore'},
                {'creation_mode': 'PointInTimeRestore', 'creation_source_cluster': SOURCE_ID,
                 'point_in_time': '2026-10-01T12:00:00Z', 'postgresql_version': '17'},
                {'creation_source_cluster': SOURCE_ID},
                {'backup_retention_days': 7},
                {'node_count': 2}):
            with self.subTest(options=options):
                executor = Executor()
                with self.assertRaises((InvalidArgumentValueError, RequiredArgumentMissingError)):
                    create(executor, **options)
                self.assertEqual(executor.writes, [])

    def test_restore_resolves_source_version_without_put_version_and_cross_subscription(self):
        result = create(self.executor, creation_mode='PointInTimeRestore', creation_source_cluster=SOURCE_ID,
                        point_in_time='2026-10-01T12:00:00Z')
        source_reads = [arguments for name, arguments in self.executor.calls
                        if name == 'horizondb cluster show' and arguments['name'] == 'source']
        self.assertEqual(source_reads[0]['subscription'], SUBSCRIPTION)
        cluster = call(self.executor, 'horizondb cluster restore')
        self.assertIsNone(cluster['postgresql_version'])
        self.assertNotIn('creation_mode', cluster)
        self.assertEqual(cluster['creation_source_cluster'], SOURCE_ID)
        self.assertEqual(cluster['point_in_time'], '2026-10-01T12:00:00+00:00')
        self.assertEqual(cluster['creation_source_cluster_location'], 'eastus2')
        self.assertEqual(result['cluster']['postgresqlVersion'], '17')

    def test_customer_managed_key_identity_is_sent_without_tags(self):
        create(self.executor, data_encryption_type='AzureKeyVault',
               primary_encryption_key_uri='https://vault.vault.azure.net/keys/key',
               primary_encryption_identity=IDENTITY_ID, user_assigned_identities=[IDENTITY_ID, IDENTITY_ID])
        cluster = call(self.executor, 'horizondb cluster create')
        self.assertEqual(cluster['mi_user_assigned'], [IDENTITY_ID])
        self.assertEqual(cluster['data_encryption']['primary_user_assigned_identity_id'], IDENTITY_ID)
        self.assertNotIn('tags', cluster)

    def test_executor_imports_nested_generated_commands_without_cli_subprocess(self):
        test_case = self
        for command, module in (
                ('horizondb cluster authentication microsoft-entra create',
                 '.aaz.latest.horizondb.cluster.authentication.microsoft_entra._create'),
                ('horizondb cluster create', '.aaz.latest.horizondb.cluster._create'),
                ('horizondb cluster restore', '.aaz.latest.horizondb.cluster._restore'),
                ('horizondb cluster pool create', '.aaz.latest.horizondb.cluster.pool._create')):
            with self.subTest(command=command):
                calls = []

                class Generated:
                    @classmethod
                    def get_arguments_schema(cls):
                        return SimpleNamespace(_fields={'state': None})

                    def __init__(self, cli_ctx, callbacks):
                        calls.append(cli_ctx)
                        test_case.assertEqual(callbacks, {})

                    def __call__(self, arguments):
                        calls.append(arguments)
                        return {'id': 'real-generated-result'}

                with patch.object(
                        workflow, 'import_module', return_value=SimpleNamespace(Create=Generated, Restore=Generated),
                ) as load:
                    result = workflow.CommandExecutor('context').run(command, state='Enabled', omitted=None)
                load.assert_called_once_with(module, 'azext_horizondb')
                self.assertEqual(calls, ['context', {'state': 'Enabled'}])
                self.assertEqual(result, {'id': 'real-generated-result'})

    def test_executor_rejects_unrecognized_fields_instead_of_silently_dropping_them(self):
        test_case = self

        class Generated:
            @classmethod
            def get_arguments_schema(cls):
                return SimpleNamespace(_fields={})

            def __init__(self, cli_ctx):
                test_case.fail('A contract mismatch must fail before invoking the generated command.')

        with patch.object(workflow, 'import_module', return_value=SimpleNamespace(Create=Generated)):
            with self.assertRaisesRegex(CLIInternalError, 'does not support workflow arguments'):
                workflow.CommandExecutor('context').run('horizondb cluster create', creation_mode='PointInTimeRestore')

    def test_discovery_uses_private_generated_class(self):
        from azext_horizondb import _discovery
        arguments = []
        test_case = self

        class Generated:
            def __init__(self, cli_ctx):
                test_case.assertEqual(cli_ctx, 'context')

            def __call__(self, command_args):
                arguments.append(command_args)
                return iter(CAPABILITIES)

        with patch.object(_discovery, 'import_module', return_value=SimpleNamespace(List=Generated)) as load:
            self.assertEqual(_discovery.list_regional_capabilities('context', 'eastus2'), CAPABILITIES)
        load.assert_called_once_with('.aaz.latest.horizondb.capability._list', 'azext_horizondb')
        self.assertEqual(arguments, [{'location': 'eastus2'}])

    def test_password_command_disables_debug_http_logging_including_polling_responses(self):
        pipeline = SimpleNamespace(run=Mock(return_value='response'))
        context = SimpleNamespace(get_http_client=Mock(return_value=SimpleNamespace(_pipeline=pipeline)))
        original = pipeline.run
        workflow._disable_authentication_logging(context)
        self.assertEqual(pipeline.run('request'), 'response')
        self.assertEqual(pipeline.run('poll', logging_enable=True), 'response')
        self.assertEqual(original.call_args_list[0].kwargs, {'logging_enable': False})
        self.assertEqual(original.call_args_list[1].kwargs, {'logging_enable': False})
        context.get_http_client.assert_called_once_with('MgmtClient')

    def test_password_executor_installs_private_pipeline_logging_callback(self):
        test_case = self

        class Generated:
            @classmethod
            def get_arguments_schema(cls):
                return SimpleNamespace(_fields={'state': None})

            def __init__(self, cli_ctx, callbacks):
                test_case.assertEqual(callbacks, {'pre_operations': workflow._disable_authentication_logging})

            def __call__(self, arguments):
                return {'state': arguments['state']}

        with patch.object(workflow, 'import_module', return_value=SimpleNamespace(Create=Generated)):
            self.assertEqual(workflow.CommandExecutor('context').run(
                'horizondb cluster authentication password create', state='Disabled'), {'state': 'Disabled'})


class CreateCommandTests(TestCase):

    def setUp(self):
        self.loader = load_commands(get_default_cli())
        self.command = self.loader.command_table['horizondb create']
        self.parser = AzCliCommandParser(cli_ctx=self.loader.cli_ctx)
        self.parser.load_command_table(self.loader)

    def test_custom_command_parser_binds_to_the_existing_workflow(self):
        namespace = self.parser.parse_args([
            'horizondb', 'create', '-g', 'rg', '-n', 'example',
            '--public-access', '203.0.113.8', '198.51.100.0/28', '--enable-ai',
            '--v-cores', '8', '--node-count', '3', '--high-availability-mode', 'AnyZone',
            '--user-assigned-identities', IDENTITY_ID,
        ])
        arguments = {
            name: value for name, value in vars(namespace).items()
            if name in self.command.arguments and value is not None
        }
        with patch.object(workflow, 'horizondb_create', autospec=True,
                          return_value={'created': True}) as create_workflow:
            self.assertEqual(self.command(dict(arguments, cmd=self.command)), {'created': True})
        create_workflow.assert_called_once_with(**arguments, cmd=self.command)
        self.assertEqual(arguments['resource_group_name'], 'rg')
        self.assertEqual(arguments['cluster_name'], 'example')
        self.assertEqual(arguments['public_access'], ['203.0.113.8', '198.51.100.0/28'])
        self.assertEqual(arguments['user_assigned_identities'], [IDENTITY_ID])
        self.assertEqual(arguments['v_cores'], 8)
        self.assertEqual(arguments['node_count'], 3)
        self.assertIs(arguments['enable_ai'], True)

    def test_root_uses_native_registration_and_preserves_defaults_without_tags_or_no_wait(self):
        self.assertNotIsInstance(self.command, AAZCommand)
        arguments = self.command.arguments
        self.assertEqual(arguments['authentication'].type.settings['default'], 'Entra')
        self.assertEqual(arguments['compute_generation'].type.settings['default'], 1)
        self.assertIs(arguments['enable_ai'].type.settings['default'], False)
        self.assertFalse(self.command.supports_no_wait)
        self.assertNotIn('tags', arguments)
        self.assertNotIn('no_wait', arguments)
        self.assertEqual(arguments['cmd'].options['help'], SUPPRESS)
        self.assertEqual(arguments['executor'].options['help'], SUPPRESS)
        self.assertEqual(arguments['cluster_name'].options_list, ['--name', '-n'])
        self.assertTrue(arguments['cluster_name'].options['required'])
        self.assertTrue(arguments['resource_group_name'].options['required'])
        self.assertIsNone(self.command.command_kwargs.get('client_factory'))

    def test_root_preserves_original_convenience_configuration_options(self):
        original_options = {
            'resource_group_name', 'cluster_name', 'location', 'postgresql_version',
            'v_cores', 'authentication', 'public_access', 'enable_ai',
            'administrator_object_id', 'administrator_principal_name', 'administrator_principal_type', 'tenant_id',
            'administrator_login', 'administrator_login_password', 'pool_name', 'node_count',
            'compute_type', 'compute_processor', 'compute_generation', 'high_availability_mode',
            'data_encryption_type', 'primary_encryption_key_uri', 'primary_encryption_identity',
            'user_assigned_identities', 'creation_mode', 'creation_source_cluster',
            'creation_source_cluster_location', 'point_in_time', 'backup_retention_days', 'geo_redundancy',
        }
        self.assertEqual(
            {name for name, argument in self.command.arguments.items()
             if argument.options.get('help') != SUPPRESS}, original_options,
        )

    def test_parser_binds_restore_encryption_and_password_options_to_the_workflow(self):
        key = 'https://example.vault.azure.net/keys/cluster'
        timestamp = '2026-10-01T12:00:00Z'
        namespace = self.parser.parse_args([
            'horizondb', 'create', '-g', 'rg', '-n', 'restored',
            '--creation-mode', 'PointInTimeRestore', '--creation-source-cluster', SOURCE_ID,
            '--creation-source-cluster-location', 'eastus2', '--point-in-time', timestamp,
            '--data-encryption-type', 'AzureKeyVault', '--primary-encryption-key-uri', key,
            '--primary-encryption-identity', IDENTITY_ID, '--user-assigned-identities', IDENTITY_ID,
            '--authentication', 'Password', '--administrator-login', 'hdbadmin',
            '--administrator-login-password', 'example-test-password', '--geo-redundancy', 'Disabled',
            '--backup-retention-days', '14',
        ])
        arguments = {
            name: value for name, value in vars(namespace).items()
            if name in self.command.arguments and value is not None
        }
        with patch.object(workflow, 'horizondb_create', autospec=True, return_value={}) as create_workflow:
            self.command(dict(arguments, cmd=self.command))
        create_workflow.assert_called_once_with(**arguments, cmd=self.command)
        self.assertEqual(arguments['creation_mode'], 'PointInTimeRestore')
        self.assertEqual(arguments['creation_source_cluster'], SOURCE_ID)
        self.assertEqual(arguments['creation_source_cluster_location'], 'eastus2')
        self.assertEqual(arguments['point_in_time'], timestamp)
        self.assertEqual(arguments['data_encryption_type'], 'AzureKeyVault')
        self.assertEqual(arguments['primary_encryption_key_uri'], key)
        self.assertEqual(arguments['primary_encryption_identity'], IDENTITY_ID)
        self.assertEqual(arguments['administrator_login_password'], 'example-test-password')
        self.assertEqual(arguments['backup_retention_days'], 14)

    def test_parser_preserves_argument_validation(self):
        cases = (
            ['--v-cores', '0'], ['--v-cores', '193'], ['--v-cores', 'invalid'],
            ['--node-count', '0'], ['--node-count', '17'], ['--compute-generation', '0'],
            ['--backup-retention-days', '0'], ['--backup-retention-days', '36'],
            ['--name', 'Invalid_Name'], ['--administrator-object-id', 'not-a-guid'],
            ['--user-assigned-identities', SOURCE_ID],
            ['--point-in-time', '2026-10-01T12:00:00+02:00'],
            ['--primary-encryption-key-uri', 'https://example.vault.azure.net/keys/key/version'],
        )
        for options in cases:
            with self.subTest(options=options), self.assertRaises(InvalidArgumentValueError):
                self.parser.parse_args(['horizondb', 'create', '-g', 'rg', '-n', 'example'] + options)


class GeneratedWire:
    """In-memory ARM transport; command, serialization, deserialization and polling are real."""

    def __init__(self):
        self.requests = []
        self.resources = {}
        self.fail_path = None
        self.source = None
        self.operation_count = 0
        self.secret_logging = []

    def run(self, request, **kwargs):
        import json
        from urllib.parse import urlparse
        from azure.core.pipeline import PipelineContext, PipelineResponse
        from azure.core.pipeline.policies import ContentDecodePolicy
        from azure.core.pipeline.transport import HttpResponse
        from requests.structures import CaseInsensitiveDict

        class Response(HttpResponse):
            def __init__(self, http_request, status, data, headers):
                super().__init__(http_request, None)
                self.status_code = status
                self.reason = 'Not Found' if status == 404 else 'OK'
                self.headers = CaseInsensitiveDict({'content-type': 'application/json', **headers})
                self._body = json.dumps(data).encode()

            def body(self):
                return self._body

        path = urlparse(request.url).path
        request.headers.setdefault('x-ms-client-request-id', SUBSCRIPTION)
        body = json.loads(request.body) if request.body else None
        self.requests.append((request.method, path, body))
        if '/authentications/passwordMethod' in path:
            self.secret_logging.append(kwargs.get('logging_enable', True))
        status, data, headers = self.respond(request.method, path, body)
        context = PipelineContext(None)
        context.options['stream'] = False
        context[ContentDecodePolicy.CONTEXT_NAME] = data
        return PipelineResponse(request, Response(request, status, data, headers), context)

    def respond(self, method, path, body):
        if self.fail_path and path.endswith(self.fail_path):
            return 500, {'error': {'code': 'InternalError', 'message': 'Injected failure'}}, {}
        if '/operations/' in path:
            return 200, {'status': 'Succeeded'}, {}
        if method in ('PUT', 'PATCH'):
            resource = deepcopy(self.resources.get(path, {}))
            resource.update({key: value for key, value in body.items() if key != 'properties'})
            resource.setdefault('properties', {}).update(body.get('properties', {}))
            resource.update(id=path, name=path.rsplit('/', 1)[-1])
            resource['properties']['provisioningState'] = 'Succeeded'
            self.resources[path] = resource
            self.operation_count += 1
            return 201 if method == 'PUT' else 202, {
                **resource, 'properties': {**resource['properties'], 'provisioningState': 'Creating'}
            }, {
                'Azure-AsyncOperation': f'https://management.azure.com/operations/{self.operation_count}',
                'Retry-After': '0',
            }
        if path in self.resources:
            return 200, self.resources[path], {}
        if path.endswith('/capabilities'):
            return 200, {'value': CAPABILITIES}, {}
        if path.endswith('/locations/eastus2/parameterGroups'):
            return 200, {'value': [{'id': DEFAULT_ID, 'name': 'pg17',
                                   'properties': {'postgreSqlVersion': '17'}}]}, {}
        if path == DEFAULT_ID:
            return 200, {'id': DEFAULT_ID, 'name': 'pg17', 'properties': {'postgreSqlVersion': '17'}}, {}
        if path.endswith('/endpoints'):
            return 200, {'value': [{'id': path + '/cluster', 'name': 'cluster',
                                   'properties': {'scope': 'Cluster', 'role': 'ReadWrite',
                                                  'fullyQualifiedDomainName': 'example.horizondb.test'}}]}, {}
        if self.source and path == self.source:
            return 200, {'id': path, 'name': 'source', 'location': 'eastus2',
                         'properties': {'postgreSqlVersion': '17'}}, {}
        return 404, {'error': {'code': 'ResourceNotFound', 'message': 'Not found'}}, {}


class GeneratedCreateWorkflowTests(TestCase):

    def setUp(self):
        from azure.cli.core.aaz._client import registered_clients
        from azure.cli.core.sdk.policies import SafeNetworkTraceLoggingPolicy

        self.wire = GeneratedWire()
        self.loader = load_commands(get_default_cli())
        self.command = self.loader.command_table['horizondb create']

        def get_client(context, client_type):
            if client_type not in context._clients:
                client = registered_clients[client_type](
                    context, credential=Mock(), logging_policy=SafeNetworkTraceLoggingPolicy())
                client._pipeline.run = self.wire.run
                context._clients[client_type] = client
            return context._clients[client_type]

        for mocked in (
                patch('azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client', new=get_client),
                patch('azure.cli.core.commands.client_factory.get_subscription_id', return_value=SUBSCRIPTION),
                patch('azure.cli.core.util.send_raw_request',
                      return_value=SimpleNamespace(json=lambda: {'location': 'eastus2'}))):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_real_generated_commands_complete_workflow_and_await_operations(self):
        for authentication in ('Password', 'Entra', 'Both'):
            with self.subTest(authentication=authentication):
                self.wire = GeneratedWire()
                administrator = None if authentication == 'Password' else {
                    'object_id': SUBSCRIPTION, 'principal_name': 'admin',
                    'principal_type': 'User', 'tenant_id': SUBSCRIPTION,
                }
                with patch.object(workflow, '_administrator', return_value=administrator):
                    result = self.command({
                        'cmd': self.command,
                        'resource_group_name': 'rg', 'cluster_name': 'example', 'authentication': authentication,
                        'public_access': ['203.0.113.8'], 'enable_ai': True,
                        **({'administrator_login_password': 'test-Password123!'} if authentication != 'Entra' else {}),
                    })
                cluster_path = (f'/subscriptions/{SUBSCRIPTION}/resourceGroups/rg/'
                                'providers/Microsoft.HorizonDb/clusters/example')
                writes = [(method, path, body) for method, path, body in self.wire.requests
                          if method in ('PUT', 'PATCH')]
                cluster_put = next(body for method, path, body in writes if method == 'PUT' and path == cluster_path)
                pool_put = next(body for method, path, body in writes if path == cluster_path + '/pools/example-pool')
                self.assertEqual(cluster_put['properties']['postgreSqlVersion'], '17')
                self.assertEqual(cluster_put['properties']['creationMode'], 'Create')
                self.assertEqual(cluster_put['properties']['network']['publicAccess'], 'Enabled')
                self.assertEqual(pool_put['properties']['computeModel'], {
                    'type': 'Provisioned', 'computeGeneration': 1, 'computeProcessor': 'AMD', 'vCores': 2,
                })
                self.assertEqual(pool_put['properties']['parameterGroup'], {
                    'parameterGroupResourceId': DEFAULT_ID, 'applyMethod': 'Immediate',
                })
                self.assertNotIn('tags', pool_put)
                self.assertNotIn('scheduledMaintenance', pool_put['properties'])
                self.assertEqual(sum(
                    '/pools/' in path and '/firewallRules/' not in path for _, path, _ in writes
                ), 1)
                self.assertTrue(any(
                    method == 'GET' and '/operations/' in path for method, path, _ in self.wire.requests
                ))
                self.assertEqual(result['aiModelManagement'], 'Enabled')
                self.assertEqual(result['connection']['endpoints'][0]['host'], 'example.horizondb.test')
                self.assertEqual(result['pool']['id'], cluster_path + '/pools/example-pool')
                self.assertNotIn('test-Password123!', repr(result))
                self.assertTrue(self.wire.secret_logging)
                self.assertFalse(any(self.wire.secret_logging))
                self.assertEqual(self.wire.operation_count, len(writes))

    def test_real_generated_restore_and_cmk_reach_wire(self):
        self.wire.source = SOURCE_ID
        result = workflow.horizondb_create(
            self.command, 'rg', 'example', authentication='Password', public_access=['203.0.113.8'],
            administrator_login_password='test-Password123!', creation_mode='PointInTimeRestore',
            creation_source_cluster=SOURCE_ID, point_in_time='2026-10-01T12:00:00Z',
            data_encryption_type='AzureKeyVault', primary_encryption_key_uri='https://vault.vault.azure.net/keys/key',
            primary_encryption_identity=IDENTITY_ID, user_assigned_identities=[IDENTITY_ID])
        cluster_put = next(body for method, path, body in self.wire.requests
                           if method == 'PUT' and path.endswith('/example'))
        self.assertEqual(cluster_put['identity'], {
            'type': 'UserAssigned', 'userAssignedIdentities': {IDENTITY_ID: {}},
        })
        properties = cluster_put['properties']
        self.assertEqual(properties['creationMode'], 'PointInTimeRestore')
        self.assertEqual(properties['creationSourceClusterResourceId'], SOURCE_ID)
        self.assertEqual(properties['creationSourceClusterLocation'], 'eastus2')
        self.assertEqual(properties['pointInTimeUtc'], '2026-10-01T12:00:00.000Z')
        self.assertNotIn('postgreSqlVersion', properties)
        self.assertEqual(properties['dataEncryption'], {
            'type': 'AzureKeyVault', 'primaryKeyUri': 'https://vault.vault.azure.net/keys/key',
            'primaryUserAssignedIdentityId': IDENTITY_ID,
        })
        self.assertEqual(result['cluster']['creationMode'], 'PointInTimeRestore')

    def test_real_generated_failure_keeps_cluster_and_stops_later_operations(self):
        self.wire.fail_path = '/pools/example-pool'
        with self.assertRaises(HttpResponseError):
            workflow.horizondb_create(
                self.command, 'rg', 'example', authentication='Password', public_access=['203.0.113.8'],
                administrator_login_password='test-Password123!')
        self.assertTrue(any(path.endswith('/clusters/example') for path in self.wire.resources))
        self.assertFalse(any(
            '/authentications/' in path or method == 'DELETE' for method, path, _ in self.wire.requests
        ))
