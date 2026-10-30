# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Generate per-command AAZ help while keeping the example inputs reproducible."""

import argparse
import ast
from pathlib import Path
import re
import shlex
import textwrap


EXAMPLES = {}
_GUID = '00000000-0000-0000-0000-000000000000'
_SUBSCRIPTION_ID = _GUID
_PROVIDER_ID = '/subscriptions/' + _SUBSCRIPTION_ID + '/resourceGroups/example-rg/providers/'
_CLUSTER_ID = _PROVIDER_ID + 'Microsoft.HorizonDb/clusters/source-cluster'
_LITERALS = {
    'SUBSCRIPTION_ID': _SUBSCRIPTION_ID,
    'TENANT_ID': _GUID,
    'IDENTITY_ID': _PROVIDER_ID + 'Microsoft.ManagedIdentity/userAssignedIdentities/example-identity',
    'PRIMARY_ENCRYPTION_ID': _PROVIDER_ID + 'Microsoft.ManagedIdentity/userAssignedIdentities/encryption-identity',
    'SOURCE_CLUSTER_ID': _CLUSTER_ID,
    'CLUSTER_ID': _CLUSTER_ID,
    'DEFAULT_PARAMETER_GROUP_ID': (
        '/subscriptions/' + _SUBSCRIPTION_ID
        + '/providers/Microsoft.HorizonDb/locations/eastus2/parameterGroups/pg17'),
    'CUSTOM_PARAMETER_GROUP_ID': _PROVIDER_ID + 'Microsoft.HorizonDb/parameterGroups/pg-custom',
    'ASSIGNMENT_ID': _CLUSTER_ID + '/changeDataCaptureDestinations/fabric-main/identityAssignments/primary',
    'DESTINATION_ID': _CLUSTER_ID + '/changeDataCaptureDestinations/fabric-main',
    'ETAG': 'example-etag',
    'HORIZONDB_ADMIN_LOGIN': 'hdbadmin',
    'HORIZONDB_ADMIN_PASSWORD': '***',
    'HORIZONDB_NEW_ADMIN_PASSWORD': '***',
}


def _examples(command, *examples):
    EXAMPLES['horizondb ' + command] = [
        {'name': title, 'text': 'az horizondb ' + command + ' '
         + re.sub(r'\$([A-Z_]+)', lambda match: _LITERALS[match[1]], arguments)}
        for title, arguments in examples
    ]


_RG = '-g example-rg'
_CLUSTER = _RG + ' --cluster-name example-cluster'
_RESOURCE = _RG + ' -n example-cluster'
_POOL = _CLUSTER + ' --pool-name primary'
_LOCATION = '-l eastus2'
_DEFAULT_GROUP = '"$DEFAULT_PARAMETER_GROUP_ID"'

_examples('create',
          ('Create a cluster with Entra authentication.', _RESOURCE),
          ('Create a cluster with public access and AI enabled.',
           _RESOURCE + ' --location indonesiacentral --public-access 203.0.113.10 198.51.100.0/28 --enable-ai'),
          ('Create a cluster with Entra and password authentication.',
           _RESOURCE + ' --authentication Both --administrator-login hdbadmin --public-access 203.0.113.10'),
          ('Create a cluster with a three-node pool.',
           _RESOURCE + ' --pool-name primary --node-count 3 --compute-processor Intel'
           ' --v-cores 8 --high-availability-mode ZoneRedundant --backup-retention-days 14'
           ' --geo-redundancy Enabled --public-access 203.0.113.10'),
          ('Create a cluster with a customer-managed key.',
           _RESOURCE + ' --data-encryption-type AzureKeyVault'
           ' --primary-encryption-key-uri https://example-vault.vault.azure.net/keys/example-key'
           ' --primary-encryption-identity "$IDENTITY_ID" --user-assigned-identities "$IDENTITY_ID"'
           ' --geo-redundancy Disabled --public-access 203.0.113.10'),
          ('Restore a cluster.',
           _RG + ' --name restored-cluster --location eastus2 --creation-mode PointInTimeRestore'
           ' --creation-source-cluster "$SOURCE_CLUSTER_ID"'
           ' --point-in-time 2026-10-01T12:00:00Z --pool-name restored-pool --public-access 203.0.113.10'))

_examples('cluster create',
          ('Create a cluster.',
           _RESOURCE + ' ' + _LOCATION + ' --postgresql-version 17 --geo-redundancy Disabled'),
          ('Create a cluster with a customer-managed key.',
           _RG + ' --name encrypted-cluster --location eastus2 --postgresql-version 17 --geo-redundancy Disabled'
           ' --user-assigned "$PRIMARY_ENCRYPTION_ID"'
           ' --data-encryption "{type:AzureKeyVault,'
           "primary-key-uri:'https://example-vault.vault.azure.net/keys/example-key',"
           'primary-user-assigned-identity-id:$PRIMARY_ENCRYPTION_ID}"'))
_examples('cluster restore',
          ('Restore a cluster in the same region.',
           _RG + ' --name restored-cluster --location eastus2'
           ' --creation-source-cluster "$SOURCE_CLUSTER_ID" --point-in-time 2026-08-30T12:00:00Z'
           ' --geo-redundancy Disabled'),
          ('Restore a cluster in another region.',
           _RG + ' --name cross-region-restored-cluster --location westus2'
           ' --creation-source-cluster "$SOURCE_CLUSTER_ID" --creation-source-cluster-location eastus2'
           ' --point-in-time 2026-08-30T12:00:00Z --geo-redundancy Disabled'))
_examples('cluster show',
          ('Show a cluster.', _RESOURCE))
_examples('cluster list',
          ('List clusters in a resource group.', _RG + ' --output table'),
          ('List clusters in a subscription.', '--subscription "$SUBSCRIPTION_ID" --output table'))
_examples('cluster update',
          ('Update public access and backup retention.',
           _RESOURCE + ' --public-access Enabled --backup-retention-days 21 --no-wait'),
          ('Enable AI model management.', _RESOURCE + ' --ai-model-management Enabled'),
          ('Update the encryption key.',
           _RG + ' --name encrypted-cluster'
           ' --data-encryption "{primary-key-uri:'
           "'https://example-vault.vault.azure.net/keys/replacement-key'}\""),
          ('Assign a managed identity.',
           _RESOURCE + ' --user-assigned "$IDENTITY_ID"'),
          ('Remove a managed identity.',
           '--ids "$CLUSTER_ID" --remove-user-assigned-identities "$IDENTITY_ID"'))
_examples('cluster delete',
          ('Delete a cluster.', _RESOURCE + ' --yes --no-wait'))
_examples('cluster failover',
          ('Fail over a cluster.', _RESOURCE + ' --no-wait'))

_COMPUTE = (' --compute-processor Intel --compute-generation 3 --v-cores 8'
            ' --node-count 3 --high-availability-mode AnyZone')
_examples('cluster pool create',
          ('Create a pool.',
           _CLUSTER + ' --name primary' + _COMPUTE),
          ('Create a pool with a default parameter group.',
           _CLUSTER + ' --name primary' + _COMPUTE + ' --parameter-group ' + _DEFAULT_GROUP
           + ' --parameter-apply-method Immediate'))
_examples('cluster pool show',
          ('Show a pool.', _CLUSTER + ' --name primary'))
_examples('cluster pool list', ('List compute pools in a cluster.', _CLUSTER + ' --output table'))
_examples('cluster pool update',
          ('Resize a pool.', _CLUSTER + ' --name primary --v-cores 32'),
          ('Enable zone-redundant high availability.',
           _CLUSTER + ' --name primary --node-count 2 --high-availability-mode ZoneRedundant --no-wait'),
          ('Disable high availability.',
           _CLUSTER + ' --name primary --node-count 1 --high-availability-mode Disabled --no-wait'),
          ('Assign a custom parameter group.',
           _CLUSTER + ' --name primary --parameter-group "$CUSTOM_PARAMETER_GROUP_ID"'
           ' --parameter-apply-method PendingReboot'),
          ('Assign the default parameter group.',
           _CLUSTER + ' --name primary --parameter-group ' + _DEFAULT_GROUP
           + ' --parameter-apply-method Immediate'))
_examples('cluster pool delete',
          ('Delete a pool.', _CLUSTER + ' --name primary --yes --no-wait'))
for _action, _title in (
        ('start', 'Start a pool.'),
        ('stop', 'Stop a pool.'),
        ('restart', 'Restart a pool.')):
    _arguments = _CLUSTER + ' --name primary' + (' --no-wait' if _action == 'stop' else '')
    _examples('cluster pool ' + _action, (_title, _arguments))
_examples('cluster pool node show',
          ('Show a node.', _POOL + ' --name node-001'))
_examples('cluster pool node list', ('List nodes in a pool.', _POOL + ' --output table'))
_examples('cluster endpoint show',
          ('Show an endpoint.', _CLUSTER + ' --name example-cluster'))
_examples('cluster endpoint list', ('List cluster and pool endpoints.', _CLUSTER + ' --output table'))
_RULE = _POOL + ' --name office-client'
_RANGE = ' --start-ip-address 203.0.113.10 --end-ip-address 203.0.113.10'
_examples('cluster pool firewall-rule create',
          ('Create a firewall rule.', _RULE + _RANGE),
          ('Replace a firewall rule.', _RULE + _RANGE + ' --description "Office egress"'))
_examples('cluster pool firewall-rule show', ('Show a firewall rule.', _RULE))
_examples('cluster pool firewall-rule list', ('List firewall rules.', _POOL + ' --output table'))
_examples('cluster pool firewall-rule delete', ('Delete a firewall rule.', _RULE + ' --yes'))
_examples('cluster pool firewall-rule update',
          ('Update a firewall rule.',
           _RULE + _RANGE + ' --description "Updated office egress"'))

_examples('cluster authentication list',
          ('List authentication settings.', _CLUSTER + ' --output table'))
_examples('cluster authentication password show',
          ('Show password authentication settings.', _CLUSTER))
_examples('cluster authentication password create',
          ('Enable password authentication.',
           _CLUSTER + ' --state Enabled --administrator-login "$HORIZONDB_ADMIN_LOGIN"'
           ' --administrator-login-password "$HORIZONDB_ADMIN_PASSWORD"'))
_examples('cluster authentication password update',
          ('Reset the administrator password.',
           _CLUSTER + ' --administrator-login-password "$HORIZONDB_NEW_ADMIN_PASSWORD"'),
          ('Disable password authentication.', _CLUSTER + ' --state Disabled'),
          ('Enable password authentication and reset the password.',
           _CLUSTER + ' --state Enabled --administrator-login-password "$HORIZONDB_NEW_ADMIN_PASSWORD" --no-wait'))
_examples('cluster authentication microsoft-entra show', ('Show Entra authentication settings.', _CLUSTER))
for _action in ('create', 'update'):
    _examples('cluster authentication microsoft-entra ' + _action,
              (('Enable' if _action == 'create' else 'Update')
               + ' Entra authentication.', _CLUSTER + ' --state Enabled'))
_ADMIN = _CLUSTER + ' --object-id ' + _GUID
_examples('cluster microsoft-entra-administrator create',
          ('Create an Entra administrator.',
           _ADMIN + ' --principal-name admin@contoso.com --principal-type User'
           ' --tenant-id "$TENANT_ID"'))
_examples('cluster microsoft-entra-administrator show', ('Show an Entra administrator.', _ADMIN))
_examples('cluster microsoft-entra-administrator list',
          ('List Entra administrators.', _CLUSTER + ' --output table'))
_examples('cluster microsoft-entra-administrator delete',
          ('Delete an Entra administrator.', _ADMIN + ' --yes'))

for _action, _title, _arguments in (
        ('show', 'Show change data capture settings.', _CLUSTER),
        ('list', 'List change data capture settings.', _CLUSTER),
        ('create', 'Enable change data capture.', _CLUSTER + ' --desired-state Enabled'),
        ('update', 'Enable automatic extension upgrades.',
         _CLUSTER + ' --auto-upgrade-extension true'),
        ('delete', 'Delete change data capture settings.', _CLUSTER + ' --yes')):
    _examples('cluster change-data-capture ' + _action, (_title, _arguments))
_DESTINATION = _CLUSTER + ' --name fabric-main'
_examples('cluster change-data-capture-destination create',
          ('Create a Fabric destination.',
           _DESTINATION + ' --destination "{fabric:{workspace-id:' + _GUID + '},protocol:Native}"'
           ' --desired-state Enabled'))
_examples('cluster change-data-capture-destination show', ('Show a destination.', _DESTINATION))
_examples('cluster change-data-capture-destination list', ('List destinations.', _CLUSTER))
_examples('cluster change-data-capture-destination update',
          ('Disable a destination.', _DESTINATION + ' --desired-state Disabled --no-wait'))
_examples('cluster change-data-capture-destination activate-identity',
          ('Activate a destination identity.',
           _DESTINATION + ' --identity-assignment "$ASSIGNMENT_ID"'
           ' --if-match "$ETAG"'))
_examples('cluster change-data-capture-destination delete',
          ('Delete a destination.', _DESTINATION + ' --yes'))
_ASSIGNMENT = _CLUSTER + ' --destination-name fabric-main --name primary'
_examples('cluster change-data-capture-destination identity-assignment create',
          ('Assign a destination identity.', _ASSIGNMENT + ' --identity "$IDENTITY_ID"'))
_examples('cluster change-data-capture-destination identity-assignment show',
          ('Show an identity assignment.', _ASSIGNMENT))
_examples('cluster change-data-capture-destination identity-assignment list',
          ('List identity assignments.', _CLUSTER + ' --destination-name fabric-main'))
_examples('cluster change-data-capture-destination identity-assignment delete',
          ('Delete an identity assignment.',
           _CLUSTER + ' --destination-name fabric-main --name retired --yes'))
_CONFIGURATION = _CLUSTER + ' --name sales'
_examples('cluster change-data-capture-configuration create',
          ('Enable database mirroring.',
           _CONFIGURATION + ' --database-name sales --destination "$DESTINATION_ID"'
           ' --usage-profile Mirroring --desired-state Enabled'))
_examples('cluster change-data-capture-configuration show',
          ('Show a mirroring configuration.', _CONFIGURATION))
_examples('cluster change-data-capture-configuration list',
          ('List mirroring configurations.', _CLUSTER))
_examples('cluster change-data-capture-configuration update',
          ('Disable database mirroring.', _CONFIGURATION + ' --desired-state Disabled'))
_examples('cluster change-data-capture-configuration delete',
          ('Delete a mirroring configuration.', _CONFIGURATION + ' --yes'))

_CONNECTION = _CLUSTER + ' --name example-pec'
_examples('cluster private-endpoint-connection show', ('Show a private endpoint connection.', _CONNECTION))
_examples('cluster private-endpoint-connection list', ('List cluster private endpoint connections.', _CLUSTER))
_examples('cluster private-endpoint-connection approve',
          ('Approve a private endpoint connection.', _CONNECTION + ' --description "Approved"'))
_examples('cluster private-endpoint-connection reject',
          ('Reject a private endpoint connection.',
           _CLUSTER + ' --name unknown-pec --description "Unrecognized"'))
_examples('cluster private-endpoint-connection delete',
          ('Delete a cluster private endpoint connection.', _CONNECTION + ' --yes'))
_examples('cluster private-link-resource show',
          ('Show a private link resource.', _CLUSTER + ' --name example-cluster'))
_examples('cluster private-link-resource list', ('List private link resources.', _CLUSTER))

_PARAMETER_GROUP = _RG + ' --name pg-transactional'
_examples('parameter-group create',
          ('Create a parameter group.',
           _PARAMETER_GROUP + ' --location eastus2 --postgresql-version 17'
           ' --parameters "[{name:shared_buffers,value:2048MB},{name:work_mem,value:64MB}]"'))
_examples('parameter-group show',
          ('Show a parameter group.', _PARAMETER_GROUP))
_examples('parameter-group list',
          ('List resource-group custom parameter groups.', _RG),
          ('List subscription custom parameter groups.', '--subscription "$SUBSCRIPTION_ID"'))
_examples('parameter-group update',
          ('Update a parameter.',
           _PARAMETER_GROUP + ' --parameters "[{name:work_mem,value:96MB}]"'))
_examples('parameter-group connection list',
          ('List connected pools.', _RG + ' --name pg-transactional'))
_examples('parameter-group delete',
          ('Delete a parameter group.', _PARAMETER_GROUP + ' --yes'))
_examples('default-parameter-group list',
          ('List default parameter groups.', _LOCATION))
_examples('default-parameter-group show',
          ('Show a default parameter group.', '--ids "$DEFAULT_PARAMETER_GROUP_ID"'))

_WAITS = {
    'cluster': (_RESOURCE, '--created'),
    'cluster pool': (_CLUSTER + ' --name primary', '--custom "state==\'Ready\'"'),
    'cluster pool firewall-rule': (_RULE, '--created'),
    'cluster authentication password': (_CLUSTER, '--updated'),
    'cluster authentication microsoft-entra': (_CLUSTER, '--updated'),
    'cluster microsoft-entra-administrator': (_ADMIN, '--created'),
    'cluster change-data-capture': (_CLUSTER, '--updated'),
    'cluster change-data-capture-destination': (_DESTINATION, '--updated'),
    'cluster change-data-capture-destination identity-assignment': (_ASSIGNMENT, '--created'),
    'cluster change-data-capture-configuration': (_CONFIGURATION, '--updated'),
    'cluster private-endpoint-connection': (
        _CONNECTION, '--custom "privateLinkServiceConnectionState.status==\'Approved\'"'),
    'parameter-group': (_PARAMETER_GROUP, '--updated'),
}
for _group, (_selectors, _condition) in _WAITS.items():
    _items = [('Wait for the resource.', _selectors + ' ' + _condition)]
    if _group == 'cluster pool':
        _items.append(('Wait for pool deletion after asynchronous delete.', _selectors + ' --deleted'))
    _examples(_group + ' wait', *_items)

_NOTES = {
    'horizondb create': (
        'Create-only: existing clusters, including partial deployments, are rejected. '
        'Waits for every setup stage; --no-wait is not supported. Defaults to signed-in Entra authentication '
        'and the detected caller IPv4. Explicit --public-access ranges bypass IP discovery. '
        'Resources are retained on failure. Credentials and tokens are never returned. '
        'Do not use --debug with credentials: expanded arguments may appear in CLI debug logs.'),
    'horizondb cluster create': (
        'Creates or replaces only the cluster resource. Create pools and configure authentication and firewall '
        'rules separately, or use az horizondb create for a fully configured cluster. '
        'The creation mode is fixed to Create. Use az horizondb cluster restore to restore from backup.'),
    'horizondb cluster restore': (
        'Creates only the target cluster resource with creation mode fixed to PointInTimeRestore. '
        'Restore copies storage, not pools, authentication, firewall rules, or other children. '
        'The PostgreSQL version comes from backup metadata and cannot be supplied. '
        'The source cluster resource ID and UTC restore timestamp are required. '
        'Same-region restore honors the timestamp. Cross-region restore requires the source location and '
        'restores the latest backup, ignoring the required timestamp.'),
    'horizondb cluster pool create': (
        'Only one pool per cluster is supported; its name must differ from the cluster name. '
        'Compute type is fixed to Provisioned. Omit both parameter-group options for service-selected defaults. '
        'For an explicit default, get its resource ID with '
        'az horizondb default-parameter-group list --location eastus2 '
        '--query "[?postgreSqlVersion==\'17\'].id | [0]" --output tsv. Pools do not support tags.'),
    'horizondb cluster pool update': (
        'Omitted PATCH values are preserved. Pair a parameter group with its apply method. '
        'Static or PendingReboot changes require a customer-initiated pool restart; start and stop do not apply them.'),
    'horizondb cluster change-data-capture-destination activate-identity': (
        'Use the resource ID from identity-assignment show and the current ETag from destination show. '
        'The assignment must be validated and belong '
        'to this destination. Attach the identity to the cluster and grant Fabric authorization separately.'),
    'horizondb cluster change-data-capture-configuration create': (
        'Use the full ARM ID of the destination. Only Fabric Native Mirroring is supported.'),
    'horizondb default-parameter-group show': (
        'Get the resource ID using az horizondb default-parameter-group list --location eastus2.'),
}


_REDESIGN_EXAMPLES = {
    'horizondb cluster create': [{
        'name': 'Create a HorizonDB cluster',
        'text': 'az horizondb cluster create --resource-group example-resource-group '
                '--name example-cluster --location eastus2 --postgresql-version 17 '
                '--geo-redundancy Enabled',
    }],
    'horizondb cluster pool create': [{
        'name': 'Create a provisioned HorizonDB pool',
        'text': 'az horizondb cluster pool create --resource-group example-resource-group '
                '--cluster-name example-cluster --name example-pool '
                '--compute-processor Intel --compute-generation 1 --v-cores 2 '
                '--node-count 1 --high-availability-mode Disabled',
    }],
}

_COMMAND_DETAILS = {
    'cluster show': 'Shows cluster configuration, its read-write pool designation, and provisioning state.',
    'cluster list': 'Lists clusters in the selected subscription. Supply --resource-group to limit the scope.',
    'cluster update':
        'Updates only the supplied cluster settings. Change the encryption key and its identity in separate requests.',
    'cluster delete': 'Deletes the cluster and its child resources. Use --no-wait to return after acceptance.',
    'cluster failover':
        'Triggers failover in the designated read-write pool. The service selects an eligible node; '
        'a target node or availability zone cannot be specified. Use --no-wait to return after acceptance.',
    'cluster pool show': 'Shows configured compute, high availability, parameter synchronization, and pool state.',
    'cluster pool list': 'Lists compute pools belonging to the specified cluster.',
    'cluster pool delete':
        'Deletes the pool, its endpoint, and firewall rules. Deleting the last pool rejects existing '
        'private endpoint connections but leaves their connection resources available for cleanup.',
    'cluster pool start':
        'Starts stopped pool compute. Starting an already-ready pool is an idempotent no-op. '
        'Pending parameter changes are not applied by start.',
    'cluster pool stop':
        'Stops and deallocates pool compute. Stopping an already-stopped pool is an idempotent no-op. '
        'Pending parameter changes remain pending.',
    'cluster pool restart':
        'Restarts PostgreSQL and applies static or PendingReboot parameter changes. '
        'With no allocated nodes, pending changes are marked InSync for future allocations.',
    'cluster pool node show': 'Shows the realized role and availability zone of the specified service-managed node.',
    'cluster pool node list': 'Lists nodes currently allocated to the specified pool and their realized roles.',
    'cluster pool firewall-rule create':
        'Creates or replaces a pool IPv4 firewall rule. Supply the complete desired address range on replacement.',
    'cluster pool firewall-rule show': 'Shows the IPv4 range and description of the specified firewall rule.',
    'cluster pool firewall-rule list': 'Lists IPv4 firewall rules belonging to the specified pool.',
    'cluster pool firewall-rule update':
        'Reads the existing firewall rule and replaces it with the requested changes using PUT, not PATCH.',
    'cluster pool firewall-rule delete': 'Removes the specified firewall rule from its pool.',
    'cluster endpoint show':
        'Shows endpoint scope, routing role, associated resource ID, and FQDN. '
        'Use the cluster name for its ReadWrite endpoint or a pool name for its ReadOnly endpoint.',
    'cluster endpoint list': 'Lists the service-generated cluster and pool connection endpoints.',
    'cluster authentication list': 'Lists the service-created passwordMethod and microsoftEntra configurations.',
    'cluster authentication password show': 'Shows password authentication state without returning stored credentials.',
    'cluster authentication password create':
        'Creates or replaces password authentication settings. Initial setup requires state Enabled, '
        'an administrator login, and a password. Disabling cannot include credentials.',
    'cluster authentication password update':
        'Changes authentication state or resets the administrator password. Omitted values are preserved. '
        'Administrator login cannot be changed, and disabling cannot include credentials.',
    'cluster authentication microsoft-entra show': 'Shows whether Microsoft Entra authentication is enabled.',
    'cluster authentication microsoft-entra create':
        'Creates or replaces the fixed Microsoft Entra authentication configuration. Supply the desired state.',
    'cluster authentication microsoft-entra update':
        'Updates Microsoft Entra authentication state. Disabling authentication does not remove database users or roles.',
    'cluster microsoft-entra-administrator create':
        'Creates or replaces an administrator mapping for a Microsoft Entra User, Group, or ServicePrincipal.',
    'cluster microsoft-entra-administrator show':
        'Shows the principal and tenant information for the specified Entra administrator mapping.',
    'cluster microsoft-entra-administrator list': 'Lists Microsoft Entra administrator mappings for the cluster.',
    'cluster microsoft-entra-administrator delete': 'Removes the specified Microsoft Entra administrator mapping.',
    'cluster change-data-capture show': 'Shows the cluster change data capture settings named default.',
    'cluster change-data-capture list': 'Lists the cluster change data capture settings.',
    'cluster change-data-capture create': 'Creates or replaces change data capture settings using the fixed name default.',
    'cluster change-data-capture update':
        'Updates change data capture desired state or extension auto-upgrade. Omitted settings are preserved.',
    'cluster change-data-capture delete':
        'Deletes the cluster change data capture settings. Remove all destinations and configurations first.',
    'cluster change-data-capture-destination create':
        'Creates or replaces a Microsoft Fabric Native destination. '
        'Changing its immutable workspace settings requires deleting and recreating the destination.',
    'cluster change-data-capture-destination show': 'Shows destination settings and the ETag used for identity activation.',
    'cluster change-data-capture-destination list': 'Lists change data capture destinations belonging to the cluster.',
    'cluster change-data-capture-destination update':
        'Changes the desired state of a Fabric destination without replacing its immutable workspace settings.',
    'cluster change-data-capture-destination delete':
        'Deletes a Fabric destination. Remove referencing configurations and identity assignments first.',
    'cluster change-data-capture-destination identity-assignment create':
        'Creates or replaces a destination identity candidate. Attach the identity to the cluster first '
        'and configure Fabric authorization separately.',
    'cluster change-data-capture-destination identity-assignment show':
        'Shows the identity reference and validation state of a destination identity assignment.',
    'cluster change-data-capture-destination identity-assignment list':
        'Lists identity candidates belonging to the specified destination.',
    'cluster change-data-capture-destination identity-assignment delete':
        'Deletes an inactive identity assignment. The active primary assignment cannot be deleted.',
    'cluster change-data-capture-configuration show': 'Shows database enrollment settings for Fabric Mirroring.',
    'cluster change-data-capture-configuration list': 'Lists database Mirroring configurations belonging to the cluster.',
    'cluster change-data-capture-configuration update':
        'Changes the desired state of database Mirroring. Omitted settings retain their current values.',
    'cluster change-data-capture-configuration delete':
        'Deletes database enrollment without deleting its Fabric mirrored-database item. '
        'Stop or detach destination-side replication first.',
    'cluster private-endpoint-connection show': 'Shows the private endpoint connection and its approval state.',
    'cluster private-endpoint-connection list': 'Lists private endpoint connections belonging to the cluster.',
    'cluster private-endpoint-connection approve':
        'Replaces connection approval state with Approved using PUT. Requires at least one pool in the cluster.',
    'cluster private-endpoint-connection reject':
        'Replaces connection approval state with Rejected using PUT. Rejection is allowed without a cluster pool.',
    'cluster private-endpoint-connection delete': 'Deletes the specified private endpoint connection resource.',
    'cluster private-link-resource show':
        'Shows private link group and DNS metadata for an endpoint. '
        'Use the cluster name for ReadWrite or a pool name for ReadOnly.',
    'cluster private-link-resource list': 'Lists private link groups and required DNS zones for cluster and pool endpoints.',
    'parameter-group create':
        'Creates or replaces a custom PostgreSQL parameter group. The PostgreSQL version is immutable after creation.',
    'parameter-group show': 'Shows effective parameter values, system defaults, and value sources.',
    'parameter-group list':
        'Lists custom parameter groups in the subscription. Supply --resource-group to limit the scope.',
    'parameter-group update':
        'Updates parameter overrides, description, or tags. Static parameter changes require a customer-initiated '
        'restart of connected pools.',
    'parameter-group connection list': 'Lists pools associated with the specified custom parameter group.',
    'parameter-group delete': 'Deletes a custom parameter group. Disconnect all associated pools before deletion.',
    'default-parameter-group list':
        'Lists read-only default parameter groups in an Azure location, with at most one group per PostgreSQL version.',
}
_COMMAND_DETAILS = {'horizondb ' + command: detail for command, detail in _COMMAND_DETAILS.items()}
_COMMAND_DETAILS.update(_NOTES)
for _group in _WAITS:
    _COMMAND_DETAILS['horizondb ' + _group + ' wait'] = (
        'Polls the resource until the selected condition succeeds. Use --custom for a JMESPath condition, '
        '--interval for the polling interval, and --timeout to limit the wait.'
    )
if set(_COMMAND_DETAILS) != set(EXAMPLES):
    raise ValueError(
        'Command help mismatch. Missing descriptions: '
        + ', '.join(sorted(set(EXAMPLES) - set(_COMMAND_DETAILS)))
        + '; missing examples: ' + ', '.join(sorted(set(_COMMAND_DETAILS) - set(EXAMPLES)))
    )


def _update_argument_help(package):
    for path in package.rglob('*.py'):
        if 'tests' in path.relative_to(package).parts:
            continue
        text = path.read_text(encoding='utf-8')
        tree = ast.parse(text)
        assignments = {
            id(item.value): item.targets[0].attr
            for item in ast.walk(tree) if isinstance(item, ast.Assign)
            and isinstance(item.value, ast.Call) and isinstance(item.targets[0], ast.Attribute)
        }
        edits = []
        lines = text.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            if not call.func.id.startswith('AAZ') or not call.func.id.endswith('Arg'):
                continue
            help_value = next((kw.value for kw in call.keywords if kw.arg == 'help'), None)
            field = assignments.get(id(call))
            if field == 'Element':
                continue
            if help_value is None and field is None:
                continue
            if help_value is not None and (
                    not isinstance(help_value, ast.Constant) or not isinstance(help_value.value, str)):
                continue
            field = field or 'value'
            label = field.replace('_', ' ').capitalize()
            description = help_value.value.strip() if help_value is not None else {
                'resource_group': 'Name of the resource group containing the HorizonDB resource.',
                'resource_group_name': 'Name of the resource group containing the HorizonDB resource.',
                'location': 'Azure region in which the resource is located.',
            }.get(field, label + ' settings for this command.')
            sentences = re.split(r'(?<=[.!?])\s+', description, maxsplit=1)
            if len(sentences) == 2 and len(sentences[0]) <= 90:
                short, long = sentences
            else:
                short = field.replace('_', ' ').capitalize() + '.'
                long = description
            line_number = help_value.lineno if help_value is not None else call.end_lineno
            indent = ' ' * (len(lines[line_number - 1]) - len(lines[line_number - 1].lstrip()))
            if help_value is None:
                indent += '    '
            rendered = ['{\n']
            for key, value in (('short-summary', short), ('long-summary', long)):
                rendered.append(indent + f"    '{key}': (\n")
                for chunk in textwrap.wrap(value, width=80, drop_whitespace=False, break_on_hyphens=False):
                    rendered.append(indent + '        ' + repr(chunk) + '\n')
                rendered.append(indent + '    ),\n')
            rendered.append(indent + '}')
            if help_value is not None:
                start = offsets[help_value.lineno - 1] + help_value.col_offset
                end = offsets[help_value.end_lineno - 1] + help_value.end_col_offset
                edits.append((start, end, ''.join(rendered)))
            else:
                end = offsets[call.end_lineno - 1] + call.end_col_offset - 1
                preceding = text[:end].rstrip()
                separator = '' if preceding.endswith(('(', ',')) else ','
                closing_indent = indent[:-4]
                insertion = separator + '\n' + indent + 'help=' + ''.join(rendered) + ',\n' + closing_indent
                edits.append((end, end, insertion))
        for start, end, replacement in sorted(edits, reverse=True):
            text = text[:start] + replacement + text[end:]
        normalized = '\n'.join(line.rstrip() for line in text.splitlines()) + '\n'
        ast.parse(normalized)
        if edits or normalized != text:
            path.write_text(normalized, encoding='utf-8', newline='\n')


_RESOURCE_LABELS = {
    '': ('a fully configured HorizonDB cluster', 'fully configured HorizonDB clusters'),
    'cluster': ('a HorizonDB cluster', 'HorizonDB clusters'),
    'cluster pool': ('a compute pool', 'compute pools'),
    'cluster pool node': ('a pool node', 'pool nodes'),
    'cluster pool firewall-rule': ('a pool firewall rule', 'pool firewall rules'),
    'cluster endpoint': ('a cluster endpoint', 'cluster endpoints'),
    'cluster authentication': ('cluster authentication', 'cluster authentication methods'),
    'cluster authentication password': ('password authentication', 'password authentication methods'),
    'cluster authentication microsoft-entra': ('Microsoft Entra authentication', 'Microsoft Entra authentication methods'),
    'cluster microsoft-entra-administrator': ('a Microsoft Entra administrator', 'Microsoft Entra administrators'),
    'cluster change-data-capture': ('change data capture', 'change data capture settings'),
    'cluster change-data-capture-destination': ('a change data capture destination', 'change data capture destinations'),
    'cluster change-data-capture-destination identity-assignment': (
        'a destination identity assignment', 'destination identity assignments'),
    'cluster change-data-capture-configuration': (
        'a change data capture configuration', 'change data capture configurations'),
    'cluster private-endpoint-connection': ('a private endpoint connection', 'private endpoint connections'),
    'cluster private-link-resource': ('a private link resource', 'private link resources'),
    'parameter-group': ('a parameter group', 'parameter groups'),
    'parameter-group connection': ('a parameter group connection', 'parameter group connections'),
    'default-parameter-group': ('a default parameter group', 'default parameter groups'),
}


def _command_summary(name):
    parts = name.split()
    singular, plural = _RESOURCE_LABELS[' '.join(parts[1:-1])]
    verb = parts[-1]
    action = {
        'failover': 'Fail over',
        'wait': 'Wait for changes to',
        'list-download-urls': 'List download URLs for',
        'activate-identity': 'Activate the identity for',
    }.get(verb, verb.capitalize())
    return f'{action} {plural if verb == "list" else singular}.'


def _wrap_example(text, width=112):
    lines = []
    line = ''
    for token in shlex.split(text, posix=False):
        if line and len(line) + len(token) + 1 > width:
            lines.append(line)
            line = token
        else:
            line = (line + ' ' + token).lstrip()
    if line:
        lines.append(line)
    return '\n'.join(lines)


def _update_custom_help(package):
    name = 'horizondb create'
    contents = ['type: command', 'short-summary: ' + _command_summary(name), 'long-summary: |']
    contents.extend('  ' + line for line in textwrap.wrap(
        _COMMAND_DETAILS[name], width=110, break_on_hyphens=False))
    contents.append('examples:')
    for example in EXAMPLES[name]:
        contents.extend(['  - name: ' + example['name'], '    text: |'])
        contents.extend('      ' + line for line in _wrap_example(example['text']).splitlines())
    header = (
        '# --------------------------------------------------------------------------------------------\n'
        '# Copyright (c) Microsoft Corporation. All rights reserved.\n'
        '# Licensed under the MIT License. See License.txt in the project root for license information.\n'
        '# --------------------------------------------------------------------------------------------\n\n'
        'from knack.help_files import helps\n\n\n'
    )
    updated = header + f'helps[{name!r}] = """\n' + '\n'.join(contents) + '\n"""\n'
    ast.parse(updated)
    (package / '_help.py').write_text(updated, encoding='utf-8', newline='\n')


def update_help(extension):
    """Emit per-command AAZ help and standard custom-command help reproducibly."""
    package = extension / 'azext_horizondb'
    _update_custom_help(package)
    custom = {
        'horizondb cluster pool create': ('_pool.py', 'PoolCreate'),
    }
    for name, examples in EXAMPLES.items():
        if name == 'horizondb create':
            continue
        parts = name.split()
        if name in custom:
            relative, class_name = custom[name]
            path = package / relative
        else:
            path = package / 'aaz' / 'latest' / Path(*[part.replace('-', '_') for part in parts[:-1]])
            path = path / ('_' + parts[-1].replace('-', '_') + '.py')
            class_name = ''.join(word.title() for word in parts[-1].split('-'))
        text = path.read_text(encoding='utf-8')
        tree = ast.parse(text)
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == class_name)
        help_assignment = next((
            item for item in node.body if isinstance(item, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'AZ_HELP' for target in item.targets)
        ), None)
        notes = _COMMAND_DETAILS[name]
        summary = _command_summary(name)
        if name in ('horizondb cluster authentication password create',
                    'horizondb cluster authentication password update'):
            notes += (
                ' Credentials are write-only secrets. Passwords in examples are redacted as "***". '
                'Use secure input for real credentials. Do not use --debug with credentials: '
                'expanded arguments may appear in CLI debug logs.'
            )
        if help_assignment is not None:
            value = next(value for key, value in zip(help_assignment.value.keys, help_assignment.value.values)
                         if isinstance(key, ast.Constant) and key.value == 'examples')
            replacement = ["        'examples': [\n"]
            for example in examples + _REDESIGN_EXAMPLES.get(name, []):
                replacement.append('            {\n')
                for key in ('name', 'text'):
                    replacement.append(f"                '{key}': (\n")
                    for chunk in textwrap.wrap(example[key], width=80, drop_whitespace=False,
                                               break_on_hyphens=False):
                        replacement.append('                    ' + repr(chunk) + '\n')
                    replacement.append('                ),\n')
                replacement.append('            },\n')
            replacement.append('        ],\n')
            lines = text.splitlines(keepends=True)
            lines[value.lineno - 1:value.end_lineno] = replacement
        else:
            doc = node.body[0]
            if not isinstance(doc, ast.Expr) or not isinstance(doc.value, ast.Constant):
                raise ValueError(f'{name} has no AAZ class docstring.')
            original = ast.get_docstring(node).split(':example:', 1)[0].strip()
            if name in ('horizondb cluster create', 'horizondb cluster restore'):
                original = ''
            paragraphs = original.split('\n\n', 1)
            if ' '.join(paragraphs[0].split()) == summary:
                original = paragraphs[1] if len(paragraphs) > 1 else ''
            details = ' '.join(original.split())
            # Earlier help wrapping split hyphenated words and option names across lines.
            details = re.sub(r'-\s+(?=\w)', '-', details)
            details = ' '.join(details.replace(notes, '').split())
            details = (details + ' ' + notes).strip()
            contents = [summary]
            if details:
                contents.extend(['', textwrap.fill(details, width=112, break_on_hyphens=False)])
            for example in examples + _REDESIGN_EXAMPLES.get(name, []):
                contents.extend(['', ':example: ' + example['name'], _wrap_example(example['text'])])
            rendered = '\n'.join('    ' + line if line else '' for line in '\n'.join(contents).splitlines())
            replacement = '    """' + rendered.lstrip() + '\n    """\n'
            lines = text.splitlines(keepends=True)
            lines[doc.lineno - 1:doc.end_lineno] = [replacement]
        updated = ''.join(lines)
        ast.parse(updated)
        if updated != text:
            path.write_text(updated, encoding='utf-8', newline='\n')
        if help_assignment is not None:
            tree = ast.parse(updated)
            node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == class_name)
            assignment = next(item for item in node.body if isinstance(item, ast.Assign)
                              and any(isinstance(target, ast.Name) and target.id == 'AZ_HELP'
                                      for target in item.targets))
            metadata = ''
            for key, value in (('short-summary', summary), ('long-summary', notes)):
                metadata += f"        '{key}': (\n"
                for chunk in textwrap.wrap(value, width=80, drop_whitespace=False, break_on_hyphens=False):
                    metadata += '            ' + repr(chunk) + '\n'
                metadata += '        ),\n'
            lines = updated.splitlines(keepends=True)
            entries = list(zip(assignment.value.keys, assignment.value.values))
            removals = []
            for index, (key, value) in enumerate(entries):
                if isinstance(key, ast.Constant) and key.value in ('short-summary', 'long-summary'):
                    following = (entries[index + 1][0] or entries[index + 1][1]
                                 if index + 1 < len(entries) else assignment.value)
                    end = following.lineno - 1 if index + 1 < len(entries) else assignment.value.end_lineno - 1
                    removals.append((key.lineno - 1, end))
            for start, end in reversed(removals):
                del lines[start:end]
            updated = ''.join(lines)
            tree = ast.parse(updated)
            node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == class_name)
            assignment = next(item for item in node.body if isinstance(item, ast.Assign)
                              and any(isinstance(target, ast.Name) and target.id == 'AZ_HELP'
                                      for target in item.targets))
            key = next(key for key in assignment.value.keys
                       if isinstance(key, ast.Constant) and key.value == 'examples')
            lines = updated.splitlines(keepends=True)
            lines[key.lineno - 1:key.lineno - 1] = [metadata]
            updated = ''.join(lines)
            ast.parse(updated)
            path.write_text(updated, encoding='utf-8', newline='\n')
    _update_argument_help(package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extension', type=Path, default=Path(__file__).resolve().parents[1])
    update_help(parser.parse_args().extension)
