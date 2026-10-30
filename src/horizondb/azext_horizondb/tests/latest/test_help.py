# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import runpy
import re
import shlex
import shutil
from argparse import SUPPRESS
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import yaml
from knack.events import EVENT_INVOKER_POST_CMD_TBL_CREATE, EVENT_INVOKER_POST_PARSE_ARGS
from knack.help_files import helps
from azure.cli.core import get_default_cli
from azure.cli.core.aaz import AAZCommand
from azure.cli.core.commands import _explode_list_args
from azure.cli.core.commands.events import EVENT_INVOKER_PRE_LOAD_ARGUMENTS
from azure.cli.core.parser import AzCliCommandParser

from azext_horizondb import HorizonDBCommandsLoader
from azext_horizondb.tests.latest import load_commands


_HELP_GENERATOR = runpy.run_path(str(Path(__file__).parents[3] / 'dev' / 'command_help.py'))
EXAMPLES = _HELP_GENERATOR['EXAMPLES']
_SUBSCRIPTION = '00000000-0000-0000-0000-000000000001'


class HelpTests(TestCase):
    def setUp(self):
        self.loader = load_commands(get_default_cli())
        self.commands = self.loader.command_table
        self.command_help = {name: self._help_info(command) for name, command in self.commands.items()}
        self.loader.cli_ctx.raise_event(EVENT_INVOKER_PRE_LOAD_ARGUMENTS, commands_loader=self.loader)
        self.loader.cli_ctx.raise_event(EVENT_INVOKER_POST_CMD_TBL_CREATE, commands_loader=self.loader)
        global_parser = AzCliCommandParser.create_global_parser(cli_ctx=self.loader.cli_ctx)
        self.parser = AzCliCommandParser(
            cli_ctx=self.loader.cli_ctx, parents=[global_parser], prog='az',
            cli_help=self.loader.cli_ctx.help_cls(cli_ctx=self.loader.cli_ctx),
        )
        self.parser.load_command_table(self.loader)
        http_client = patch(
            'azure.cli.core.aaz._command_ctx.AAZCommandCtx.get_http_client',
            side_effect=AssertionError('Help tests must not use Azure credentials or HTTP clients.'),
        )
        http_client.start()
        self.addCleanup(http_client.stop)

    @staticmethod
    def _help_info(command):
        if isinstance(command, AAZCommand):
            return command.help
        return yaml.safe_load(helps[command.name])

    def test_generated_help_matches_canonical_examples(self):
        for name, examples in EXAMPLES.items():
            with self.subTest(command=name):
                actual = self.command_help[name]['examples'][:len(examples)]
                self.assertEqual(
                    [(item['name'], ' '.join(shlex.split(item['text']))) for item in examples],
                    [(item['name'], ' '.join(shlex.split(item['text']))) for item in actual],
                )

    def test_every_public_command_has_examples_including_redesign_extras(self):
        self.assertEqual(set(self.commands), set(EXAMPLES))
        self.assertEqual(83, len(self.commands))
        self.assertEqual(107, sum(len(help_info['examples']) for help_info in self.command_help.values()))

    def test_private_endpoint_surface_is_preserved_except_redundant_state_verbs(self):
        prefix = 'horizondb cluster private-endpoint-connection'
        supported = {'approve', 'reject', 'show', 'list', 'delete', 'wait'}
        action_args = [(prefix + ' ' + action).split() for action in supported | {'create', 'update'}]
        for args in (None, prefix.split(), *action_args):
            with self.subTest(args=args):
                loader = HorizonDBCommandsLoader(cli_ctx=get_default_cli())
                commands = loader.load_command_table(args)
                actual = {
                    name[len(prefix) + 1:] for name in commands if name.startswith(prefix + ' ')
                }
                # The CLI intentionally trims a bare group prefix to one
                # representative command; full and action loads retain all.
                if args == prefix.split():
                    self.assertTrue(actual)
                    self.assertLessEqual(actual, supported)
                else:
                    self.assertEqual(supported, actual)
                for table in (commands, loader.command_group_table):
                    for action in ('create', 'update'):
                        self.assertNotIn(prefix + ' ' + action, table)
                self.assertIn('horizondb cluster pool create', commands)

    def test_private_endpoint_redundant_state_verbs_fail_parser_recognition(self):
        for action in ('create', 'update'):
            with self.subTest(action=action):
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    with self.assertRaises(SystemExit) as result:
                        self.parser.parse_args(['horizondb', 'cluster', 'private-endpoint-connection', action])
                self.assertEqual(2, result.exception.code)

    def test_private_endpoint_group_help_only_lists_supported_commands(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            with self.assertRaises(SystemExit) as result:
                self.parser.parse_args(['horizondb', 'cluster', 'private-endpoint-connection', '--help'])
        self.assertEqual(0, result.exception.code)
        for action in ('approve', 'reject', 'show', 'list', 'delete', 'wait'):
            self.assertRegex(output.getvalue(), rf'(?m)^\s+{action}\s+(?:\[Preview\]\s+)?:')
        for action in ('create', 'update'):
            self.assertNotRegex(output.getvalue(), rf'(?m)^\s+{action}\s+(?:\[Preview\]\s+)?:')

    def test_unimplemented_log_groups_are_not_registered(self):
        for group, actions in (
                ('log-capture-configuration', ('show', 'list', 'update', 'wait')),
                ('log-file', ('show', 'list', 'list-download-urls'))):
            prefix = 'horizondb cluster ' + group
            for args in (None, prefix.split(), *[(prefix + ' ' + action).split() for action in actions]):
                with self.subTest(group=group, args=args):
                    loader = HorizonDBCommandsLoader(cli_ctx=get_default_cli())
                    commands = loader.load_command_table(args)
                    for table in (commands, loader.command_group_table):
                        self.assertFalse(any(
                            name == prefix or name.startswith(prefix + ' ') for name in table
                        ))
                    self.assertIn('horizondb cluster pool create', commands)

    def test_unimplemented_log_commands_fail_parser_recognition(self):
        for group, actions in (
                ('log-capture-configuration', ('show', 'list', 'update', 'wait')),
                ('log-file', ('show', 'list', 'list-download-urls'))):
            for action in actions:
                with self.subTest(group=group, action=action):
                    output = StringIO()
                    with redirect_stdout(output), redirect_stderr(output):
                        with self.assertRaises(SystemExit) as result:
                            self.parser.parse_args(['horizondb', 'cluster', group, action])
                    self.assertEqual(2, result.exception.code)

    def test_group_help_does_not_advertise_unimplemented_logs(self):
        for args in (['horizondb', '--help'], ['horizondb', 'cluster', '--help']):
            with self.subTest(args=args):
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    with self.assertRaises(SystemExit) as result:
                        self.parser.parse_args(args)
                self.assertEqual(0, result.exception.code)
                self.assertNotIn('log-capture-configuration', output.getvalue())
                self.assertNotIn('log-file', output.getvalue())

    def test_example_descriptions_stay_concise(self):
        for name, help_info in self.command_help.items():
            for example in help_info['examples']:
                with self.subTest(command=name, example=example['name']):
                    self.assertLessEqual(len(example['name']), 72)
                    self.assertNotIn('--query', example['name'])
                    self.assertNotIn(';', example['name'])

    def test_examples_are_self_contained_fake_literals_not_environment_references(self):
        for name, help_info in self.command_help.items():
            for example in help_info['examples']:
                with self.subTest(command=name, example=example['name']):
                    self.assertNotIn('$', example['text'])
                    self.assertNotIn('%LOG_', example['text'])

    def test_all_example_guids_are_zero_initialized(self):
        pattern = r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
        for name, help_info in self.command_help.items():
            for example in help_info['examples']:
                with self.subTest(command=name, example=example['name']):
                    for guid in re.findall(pattern, example['text']):
                        self.assertEqual('00000000-0000-0000-0000-000000000000', guid)

    def test_commands_have_short_and_long_help_and_resource_arguments_are_documented(self):
        framework_args = {
            'no_wait', 'created', 'updated', 'deleted', 'exists', 'custom', 'interval', 'timeout',
        }
        for name, command in self.commands.items():
            with self.subTest(command=name):
                self.assertTrue(self.command_help[name]['short-summary'])
                self.assertTrue(self.command_help[name]['long-summary'])
                self.assertLessEqual(len(self.command_help[name]['short-summary']), 100)
                self.assertLess(
                    len(self.command_help[name]['short-summary']), len(self.command_help[name]['long-summary']),
                )
            if not isinstance(command, AAZCommand):
                for field, argument in command.arguments.items():
                    if argument.options.get('help') == SUPPRESS:
                        continue
                    with self.subTest(command=name, argument=field):
                        self.assertTrue(argument.options.get('help'))
                continue
            for field, argument in command.get_arguments_schema()._fields.items():
                if not argument._registered or field in framework_args:
                    continue
                if field.startswith(('generic_update_', 'pagination_')):
                    continue
                with self.subTest(command=name, argument=field):
                    self.assertTrue(argument._help.get('short-summary'))
                    self.assertTrue(argument._help.get('long-summary'))

    def test_long_descriptions_are_specific_to_the_command_action(self):
        failover = ' '.join(self.commands['horizondb cluster failover'].help['long-summary'].split())
        self.assertIn('Triggers failover', failover)
        self.assertIn('service selects an eligible node', failover)
        self.assertNotIn('delet', failover.lower())
        self.assertIn('Deletes the cluster', self.commands['horizondb cluster delete'].help['long-summary'])
        descriptions = [
            help_info['long-summary'] for name, help_info in self.command_help.items() if not name.endswith(' wait')
        ]
        self.assertEqual(len(descriptions), len(set(descriptions)),
                         'Resource commands must not share a generic group description.')

    def test_entra_update_uses_concise_summary_and_preserves_api_details_in_long_help(self):
        help_info = self.commands['horizondb cluster authentication microsoft-entra update'].help
        self.assertEqual('Update Microsoft Entra authentication.', help_info['short-summary'])
        self.assertIn('State Enabled enables the feature', help_info['long-summary'])
        self.assertIn('pgaadauth extension functions', help_info['long-summary'])

    def test_cluster_create_examples_and_help_have_no_pool_creation(self):
        command = self.commands['horizondb cluster create']
        self.assertNotIn('defaultpool', command.help['long-summary'])
        for example in command.help['examples']:
            with self.subTest(example=example['name']):
                self.assertNotIn('--pool-', example['text'])
                self.assertNotIn('--compute-', example['text'])
                self.assertNotIn('default pool', example['name'])

    def test_minimal_create_and_restore_produce_valid_cluster_requests(self):
        source_id = (
            '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example-rg/'
            'providers/Microsoft.HorizonDb/clusters/source'
        )
        for verb, options, mode in (
                ('create', '--postgresql-version 17', 'Create'),
                ('restore', '--creation-source-cluster ' + source_id
                 + ' --point-in-time 2026-10-01T12:00:00Z', 'PointInTimeRestore')):
            with self.subTest(command=verb):
                name = 'horizondb cluster ' + verb
                command = self._prepare_example(name, {
                    'text': 'az ' + name + ' -g example-rg -n target -l eastus2 ' + options,
                })
                with patch.object(command.ctx, 'get_http_client'):
                    body = command.ClustersCreateOrReplace(ctx=command.ctx).content
                self.assertEqual('eastus2', body['location'])
                self.assertEqual(mode, body['properties']['creationMode'])
                self.assertNotIn('backup', body['properties'])

    def test_every_example_parses_and_validates_against_its_actual_command(self):
        for name, help_info in self.command_help.items():
            for example in help_info['examples']:
                with self.subTest(command=name, example=example['name']):
                    self._prepare_example(name, example)

    def _prepare_example(self, name, example):
        command = self.commands[name]
        tokens = shlex.split(example['text'])
        if '--administrator-login-password' in tokens:
            index = tokens.index('--administrator-login-password') + 1
            self.assertEqual('***', tokens[index])
            # Validate the schema with an in-memory value; published examples stay redacted.
            tokens[index] = 'redacted-value-for-schema-tests'
        self.assertEqual(tokens[:len(name.split()) + 1], ['az'] + name.split())
        with patch('azure.cli.core._profile.Profile.load_cached_subscriptions',
                   return_value=[{'id': _SUBSCRIPTION, 'name': 'example'}]):
            namespace = self.parser.parse_args(tokens[1:])
        self.loader.cli_ctx.raise_event(EVENT_INVOKER_POST_PARSE_ARGS, command=name, args=namespace)
        expanded = list(_explode_list_args(namespace))
        self.assertEqual(1, len(expanded))
        arguments = {
            key: value for key, value in vars(expanded[0]).items()
            if key in command.arguments and value is not None
        }
        arguments['subscription'] = _SUBSCRIPTION
        if not isinstance(command, AAZCommand):
            return command
        # Initialize and validate AAZ values without executing an operation or discovery.
        AAZCommand._handler(command, arguments)  # pylint: disable=protected-access
        command.ctx.args.to_serialized_data()
        if name in ('horizondb cluster create', 'horizondb cluster update',
                    'horizondb cluster pool create', 'horizondb cluster pool update'):
            command.pre_operations()
        return command

    def _example_content(self, name, title, operation_name):
        example = next(item for item in self.commands[name].help['examples'] if item['name'] == title)
        command = self._prepare_example(name, example)
        with patch.object(command.ctx, 'get_http_client'):
            operation = getattr(command, operation_name)(ctx=command.ctx)
        return operation.content

    def test_key_rotation_example_changes_the_key_not_backup_retention(self):
        content = self._example_content(
            'horizondb cluster update', 'Update the encryption key.', 'ClustersUpdate')
        self.assertEqual({'properties': {'dataEncryption': {
            'primaryKeyUri': 'https://example-vault.vault.azure.net/keys/replacement-key',
        }}}, content)

    def test_backup_example_changes_backup_retention_and_public_access(self):
        content = self._example_content(
            'horizondb cluster update', 'Update public access and backup retention.', 'ClustersUpdate')
        self.assertEqual({'properties': {
            'backup': {'retentionDays': 21}, 'network': {'publicAccess': 'Enabled'},
        }}, content)

    def test_high_availability_examples_match_their_descriptions(self):
        for title, count, mode in (
                ('Enable zone-redundant high availability.', 2, 'ZoneRedundant'),
                ('Disable high availability.', 1, 'Disabled')):
            with self.subTest(example=title):
                content = self._example_content('horizondb cluster pool update', title, 'PoolsUpdate')
                self.assertEqual({'properties': {'nodeCount': count, 'highAvailability': {'mode': mode}}}, content)

    def test_parameter_example_updates_the_named_parameter(self):
        content = self._example_content(
            'horizondb parameter-group update', 'Update a parameter.', 'ParameterGroupsUpdate')
        self.assertEqual({'properties': {'parameters': [{'name': 'work_mem', 'value': '96MB'}]}}, content)

    def test_destination_example_configures_fabric_native(self):
        content = self._example_content(
            'horizondb cluster change-data-capture-destination create',
            'Create a Fabric destination.', 'ChangeDataCaptureDestinationsCreateOrReplace')
        self.assertEqual({'properties': {
            'desiredState': 'Enabled',
            'destination': {'destinationType': 'Fabric', 'protocol': 'Native',
                            'workspaceId': '00000000-0000-0000-0000-000000000000'},
        }}, content)

    def test_argument_guided_loading_keeps_examples_without_duplication(self):
        for name in self.commands:
            with self.subTest(command=name):
                loader = HorizonDBCommandsLoader(cli_ctx=get_default_cli())
                command = loader.load_command_table(name.split())[name]
                self.assertEqual(self.command_help[name], self._help_info(command))

    def test_rendered_help_includes_examples_and_both_short_and_long_options(self):
        for name, options in {
            'horizondb create': ('--resource-group', '-g', '--name', '-n'),
            'horizondb cluster create': ('--resource-group', '-g', '--name', '-n', '--no-wait'),
            'horizondb cluster pool create': ('--resource-group', '-g', '--name', '-n'),
            'horizondb parameter-group update': ('--parameters',),
        }.items():
            with self.subTest(command=name):
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    with self.assertRaises(SystemExit) as result:
                        self.parser.parse_args(name.split() + ['--help'])
                self.assertEqual(0, result.exception.code)
                rendered = ' '.join(output.getvalue().split())
                for example in self.command_help[name]['examples']:
                    self.assertIn(example['name'].rstrip('.'), rendered)
                for option in options:
                    self.assertIn(option, rendered)

    def test_help_generation_is_reproducible_and_idempotent(self):
        extension = Path(__file__).parents[3]
        with TemporaryDirectory() as temporary:
            target = Path(temporary) / 'horizondb'
            shutil.copytree(extension / 'azext_horizondb', target / 'azext_horizondb',
                            ignore=shutil.ignore_patterns('__pycache__', 'tests'))
            files = list((target / 'azext_horizondb').rglob('*.py'))
            before = {path: path.read_bytes() for path in files}
            for _ in range(2):
                _HELP_GENERATOR['update_help'](target)
                self.assertEqual(before, {path: path.read_bytes() for path in files})

    def test_password_examples_are_redacted_and_explain_debug_risks(self):
        for name in ('horizondb cluster authentication password create',
                     'horizondb cluster authentication password update'):
            self.assertIn('Do not use --debug', self.commands[name].help['long-summary'])
            for example in self.commands[name].help['examples']:
                if '--administrator-login-password' in example['text']:
                    self.assertRegex(example['text'], r'--administrator-login-password\s+"\*{3}"')
