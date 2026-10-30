# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.commands.parameters import get_enum_type, get_location_type, resource_group_name_type

from ._validators import bounded_int, dns_name, guid, identity_reference, key_uri, resource_reference, utc_datetime


def load_arguments(self, _):
    with self.argument_context('horizondb create') as context:
        context.ignore('cmd')
        context.ignore('executor')
        context.argument(
            'resource_group_name', arg_type=resource_group_name_type,
            help='Name of the resource group in which to create the cluster.')
        context.argument(
            'cluster_name', options_list=['--name', '-n'], type=dns_name,
            help='Name of the new cluster. Existing clusters cannot be overwritten.')
        context.argument(
            'location', arg_type=get_location_type(self.cli_ctx),
            help='Azure region. Defaults to the resource group region when omitted.')
        context.argument(
            'postgresql_version', help='PostgreSQL major version. Defaults to 17 for new clusters. Omit for restore.')
        context.argument(
            'authentication', arg_type=get_enum_type(['Entra', 'Password', 'Both']),
            help='Authentication method. Defaults to Entra.')
        context.argument(
            'administrator_object_id', type=guid, help='Object ID of the Entra administrator principal.')
        context.argument('administrator_principal_name', help='Name of the Entra administrator principal.')
        context.argument(
            'administrator_principal_type', arg_type=get_enum_type(['User', 'Group', 'ServicePrincipal']),
            help='Type of the Entra administrator principal.')
        context.argument(
            'tenant_id', type=guid, help='Tenant GUID for the Entra administrator. Defaults to the subscription tenant.')
        context.argument('administrator_login', help='Initial password-authentication login name.')
        context.argument(
            'administrator_login_password', help='Initial password. If required but omitted, prompts securely.')
        context.argument(
            'pool_name', type=dns_name, help='Pool name. Defaults to the first 58 cluster-name characters plus -pool.')
        context.argument(
            'compute_type', arg_type=get_enum_type(['Provisioned']), help='Compute type. Provisioned is supported.')
        context.argument(
            'compute_processor', arg_type=get_enum_type(['Intel', 'AMD']),
            help='Compute processor. Omission selects compatible regional compute.')
        context.argument(
            'high_availability_mode', arg_type=get_enum_type(['Disabled', 'AnyZone', 'ZoneRedundant']),
            help='High availability mode. Disabled for one node; AnyZone or ZoneRedundant for multiple nodes.')
        context.argument(
            'data_encryption_type', arg_type=get_enum_type(['SystemManaged', 'AzureKeyVault']),
            help='Encryption type. SystemManaged by default, or AzureKeyVault for a customer key.')
        context.argument(
            'primary_encryption_key_uri', type=key_uri,
            help='Versionless HTTPS Key Vault key URI. Required with AzureKeyVault encryption.')
        context.argument(
            'primary_encryption_identity', type=identity_reference,
            help='Full ARM ID of the attached user-assigned identity used to access the encryption key.')
        context.argument(
            'creation_mode', arg_type=get_enum_type(['Create', 'PointInTimeRestore']),
            help='Creation mode. Create by default, or PointInTimeRestore to restore cluster storage.')
        context.argument(
            'creation_source_cluster', type=resource_reference, help='Full ARM ID of the source cluster for restore.')
        context.argument(
            'creation_source_cluster_location', help='Actual source cluster region. Required for cross-region restore.')
        context.argument(
            'point_in_time', type=utc_datetime,
            help='UTC restore timestamp. Cross-region restore uses the latest available backup.')
        context.argument(
            'geo_redundancy', arg_type=get_enum_type(['Enabled', 'Disabled']),
            help='Backup geo-redundancy. Must be Disabled with AzureKeyVault encryption.')
        context.argument(
            'v_cores', type=bounded_int(1, 192), help='vCores per node. Omission selects the smallest compatible size.')
        context.argument(
            'node_count', type=bounded_int(1, 16),
            help='Node count. One by default. Multiple nodes require AnyZone or ZoneRedundant high availability.')
        context.argument(
            'compute_generation', type=bounded_int(1), help='Compute generation. Generation 1 by default.')
        context.argument(
            'backup_retention_days', type=bounded_int(1, 35),
            help='Backup retention in days, from 1 to 35. Also supply --geo-redundancy.')
        context.argument(
            'public_access', nargs='+',
            help='Allowed IPv4 addresses, CIDRs, or start-end ranges. Omission detects only the caller IPv4.')
        context.argument(
            'user_assigned_identities', nargs='+', type=identity_reference,
            help='Full ARM IDs of user-assigned identities to attach.')
        context.argument(
            'enable_ai', action='store_true', help='Opt in to AI Model Management. Disabled by default.')
