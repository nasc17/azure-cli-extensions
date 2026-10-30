# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.aaz import AAZListArg, AAZResourceIdArg
from azure.cli.core.azclierror import InvalidArgumentValueError

from .aaz.latest.horizondb.cluster import Update as _ClusterUpdate
from ._validators import identity_reference


class ClusterUpdate(_ClusterUpdate):
    _arguments_schema = None
    _args_schema = None

    @classmethod
    def _build_arguments_schema(cls, *args, **kwargs):
        schema = super()._build_arguments_schema(*args, **kwargs)
        schema.remove_user_assigned_identities = AAZListArg(
            options=['--remove-user-assigned-identities'],
            arg_group='Identity',
            help={
                'short-summary': (
                    'Remove user assigned identities.'
                ),
                'long-summary': (
                    'Full ARM IDs of unreferenced user-assigned identities to remove with null PATCH '
                    'entries.'
                ),
            },
        )
        schema.remove_user_assigned_identities.Element = AAZResourceIdArg()
        return schema

    def pre_operations(self):
        removals = self.ctx.args.remove_user_assigned_identities.to_serialized_data() or []
        additions = self.ctx.args.mi_user_assigned.to_serialized_data() or []
        for resource_id in removals:
            identity_reference(resource_id)
        if {value.lower() for value in removals} & {value.lower() for value in additions}:
            raise InvalidArgumentValueError('An identity cannot be assigned and removed in the same update.')

    class ClustersUpdate(_ClusterUpdate.ClustersUpdate):
        @property
        def content(self):
            content = super().content
            removals = self.ctx.args.remove_user_assigned_identities.to_serialized_data()
            if removals:
                # The generated identity helper only adds identities; PATCH removal needs explicit nulls.
                identity = content.setdefault('identity', {})
                identity.setdefault('type', 'UserAssigned')
                identity.setdefault('userAssignedIdentities', {}).update(
                    {resource_id: None for resource_id in removals}
                )
            return content
