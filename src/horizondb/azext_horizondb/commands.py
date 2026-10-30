# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.commands import CliCommandType


def load_command_table(self, _):
    # These APIs return HTTP 501. Remove their generated registrations until
    # the backend implements them; hiding help alone would leave them callable.
    unsupported_groups = (
        'horizondb cluster log-capture-configuration',
        'horizondb cluster log-file',
    )
    # Approval and rejection are the only supported state-change interfaces.
    # Keep the generated assets available without exposing redundant PUT verbs.
    unsupported_commands = (
        'horizondb cluster private-endpoint-connection create',
        'horizondb cluster private-endpoint-connection update',
    )
    for table in (self.command_table, self.command_group_table):
        for name in list(table):
            if name in unsupported_commands or any(
                    name == group or name.startswith(group + ' ') for group in unsupported_groups):
                del table[name]

    custom = CliCommandType(operations_tmpl='azext_horizondb._create#{}')
    with self.command_group('horizondb', custom_command_type=custom, is_preview=True) as group:
        group.custom_command('create', 'horizondb_create')

    from ._cluster import ClusterUpdate
    from ._pool import PoolCreate, PoolUpdate
    self.command_table['horizondb cluster update'] = ClusterUpdate(loader=self)
    self.command_table['horizondb cluster pool create'] = PoolCreate(loader=self)
    self.command_table['horizondb cluster pool update'] = PoolUpdate(loader=self)
