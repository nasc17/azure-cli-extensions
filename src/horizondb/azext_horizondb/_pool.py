# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.cli.core.aaz import has_value

from .aaz.latest.horizondb.cluster.pool import Create as _PoolCreate, Show as _PoolShow, Update as _PoolUpdate


def validate_pool_configuration(args, prefix='--', pool_name=None):
    node_count = args.node_count.to_serialized_data() if has_value(args.node_count) else None
    mode = args.high_availability_mode.to_serialized_data() if has_value(args.high_availability_mode) else None
    if node_count == 1 and mode is not None and mode != 'Disabled':
        raise InvalidArgumentValueError(
            f'{prefix}high-availability-mode must be Disabled when {prefix}node-count is 1.'
        )
    if node_count is not None and node_count > 1 and mode == 'Disabled':
        raise InvalidArgumentValueError(
            f'{prefix}high-availability-mode must be AnyZone or ZoneRedundant '
            f'when {prefix}node-count is greater than 1.'
        )
    if pool_name is None:
        pool_name = args.name.to_serialized_data()
    if pool_name == args.cluster_name.to_serialized_data():
        raise InvalidArgumentValueError('The pool name must differ from the cluster name.')


class PoolCreate(_PoolCreate):
    AZ_HELP = {
        **_PoolCreate.AZ_HELP,
        'short-summary': (
            'Create a compute pool.'
        ),
        'long-summary': (
            'Only one pool per cluster is supported; its name must differ from the cluster '
            'name. Compute type is fixed to Provisioned. Omit both parameter-group options '
            'for service-selected defaults. For an explicit default, get its resource ID with'
            ' az horizondb default-parameter-group list --location eastus2 --query '
            '"[?postgreSqlVersion==\'17\'].id | [0]" --output tsv. Pools do not support tags.'
        ),
        'examples': [
            {
                'name': (
                    'Create a pool.'
                ),
                'text': (
                    'az horizondb cluster pool create -g example-rg --cluster-name example-cluster '
                    '--name primary --compute-processor Intel --compute-generation 3 --v-cores 8 '
                    '--node-count 3 --high-availability-mode AnyZone'
                ),
            },
            {
                'name': (
                    'Create a pool with a default parameter group.'
                ),
                'text': (
                    'az horizondb cluster pool create -g example-rg --cluster-name example-cluster '
                    '--name primary --compute-processor Intel --compute-generation 3 --v-cores 8 '
                    '--node-count 3 --high-availability-mode AnyZone --parameter-group "/subscription'
                    's/00000000-0000-0000-0000-000000000000/providers/Microsoft.HorizonDb/locations/e'
                    'astus2/parameterGroups/pg17" --parameter-apply-method Immediate'
                ),
            },
            {
                'name': (
                    'Create a provisioned HorizonDB pool'
                ),
                'text': (
                    'az horizondb cluster pool create --resource-group example-resource-group '
                    '--cluster-name example-cluster --name example-pool --compute-processor Intel '
                    '--compute-generation 1 --v-cores 2 --node-count 1 --high-availability-mode '
                    'Disabled'
                ),
            },
        ],
    }

    _arguments_schema = None
    _args_schema = None

    @classmethod
    def _build_arguments_schema(cls, *args, **kwargs):
        args_schema = super()._build_arguments_schema(*args, **kwargs)
        if hasattr(args_schema, 'scheduled_maintenance'):
            args_schema.scheduled_maintenance._registered = False  # pylint: disable=protected-access
        return args_schema

    def pre_operations(self):
        validate_pool_configuration(self.ctx.args)
        group = self.ctx.args.parameter_group.to_serialized_data()
        apply_method = self.ctx.args.parameter_apply_method.to_serialized_data()
        if bool(group) != bool(apply_method):
            raise InvalidArgumentValueError(
                'Supply --parameter-group and --parameter-apply-method together.'
            )

    class PoolsCreateOrReplace(_PoolCreate.PoolsCreateOrReplace):

        @property
        def content(self):
            content = super().content
            properties = content.setdefault('properties', {})
            properties.setdefault('computeModel', {})['type'] = 'Provisioned'
            if not properties.get('parameterGroup', {}).get('parameterGroupResourceId'):
                properties.pop('parameterGroup', None)
            return content


class PoolUpdate(_PoolUpdate):
    _arguments_schema = None
    _args_schema = None

    @classmethod
    def _build_arguments_schema(cls, *args, **kwargs):
        args_schema = super()._build_arguments_schema(*args, **kwargs)
        if hasattr(args_schema, 'scheduled_maintenance'):
            args_schema.scheduled_maintenance._registered = False  # pylint: disable=protected-access
        return args_schema

    def pre_operations(self):
        # A partial PATCH preserves omitted values; validate only supplied tuples.
        validate_pool_configuration(self.ctx.args)

    def _output(self, *args, **kwargs):
        command_args = {
            name: getattr(self.ctx.args, name).to_serialized_data()
            for name in ['cluster_name', 'name', 'resource_group']
        }
        command_args['subscription'] = self.ctx.subscription_id
        return _PoolShow(cli_ctx=self.cli_ctx)(command_args=command_args)
