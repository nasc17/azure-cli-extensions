# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Awaited, create-only convenience workflow implemented with generated AAZ commands."""

from contextlib import contextmanager
from datetime import datetime
from importlib import import_module
import ipaddress

from azure.cli.core.aaz._poller import AAZLROPoller
from azure.cli.core.azclierror import (
    AzureResponseError, CLIInternalError, InvalidArgumentValueError, RequiredArgumentMissingError)
from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.core.tools import parse_resource_id
from knack.log import get_logger

from ._validators import bounded_int, dns_name, guid, identity_reference, key_uri, resource_reference, utc_datetime


logger = get_logger(__name__)


def _properties(resource):
    # Generated command output flattens ARM properties; discovery fixtures may retain the wire wrapper.
    return (resource or {}).get('properties', resource or {}) or {}


class CommandExecutor:
    """Invoke raw generated resource commands and await each setup stage."""

    def __init__(self, cli_ctx):
        self.cli_ctx = cli_ctx

    def run(self, command, **arguments):
        parts = command.replace('-', '_').split()
        module = import_module('.aaz.latest.' + '.'.join(parts[:-1]) + '._' + parts[-1], __package__)
        command_type = getattr(module, ''.join(word.title() for word in parts[-1].split('_')))
        arguments = {key: value for key, value in arguments.items() if value is not None}
        # AAZ intentionally ignores unknown direct-call arguments. Fail closed rather than silently
        # omitting a restore, encryption or authentication setting when the generated contract changes.
        unknown = set(arguments) - set(command_type.get_arguments_schema()._fields) - {'subscription'}
        if unknown:
            raise CLIInternalError(
                f'The generated {command} contract does not support workflow arguments: {", ".join(sorted(unknown))}.')
        callbacks = ({'pre_operations': _disable_authentication_logging}
                     if ' authentication password ' in command else {})
        result = command_type(cli_ctx=self.cli_ctx, callbacks=callbacks)(arguments)
        if isinstance(result, AAZLROPoller):
            result = result.result()
        if command.endswith(' list'):
            return list(result)
        return result

    def resource_group(self, name):
        from azure.cli.core.commands.client_factory import get_subscription_id
        from azure.cli.core.util import send_raw_request
        from urllib.parse import quote
        subscription = get_subscription_id(self.cli_ctx)
        url = (self.cli_ctx.cloud.endpoints.resource_manager.rstrip('/') +
               f'/subscriptions/{subscription}/resourceGroups/{quote(name, safe="")}?api-version=2021-04-01')
        return send_raw_request(self.cli_ctx, 'GET', url).json()

    def capabilities(self, location):
        from ._discovery import list_regional_capabilities
        return list_regional_capabilities(self.cli_ctx, location)


def _disable_authentication_logging(ctx):
    """Keep credential-bearing requests AND final LRO responses out of --debug traces."""
    client = ctx.get_http_client('MgmtClient')
    # This pipeline belongs only to this generated command's context, not a shared CLI client.
    # Apply at Pipeline.run so polling requests cannot re-enable response-body logging.
    pipeline = client._pipeline  # pylint: disable=protected-access
    run = pipeline.run

    def run_without_logging(*args, **kwargs):
        kwargs['logging_enable'] = False
        return run(*args, **kwargs)

    pipeline.run = run_without_logging


@contextmanager
def _stage(name):
    logger.info('HorizonDB create: %s.', name)
    try:
        yield
    except Exception:
        # Never interpolate a response or credentials into the recovery message.
        logger.error('HorizonDB create failed during %s. Created resources have been retained for manual recovery; '
                     'inspect them with the individual commands. This command cannot resume partial creation.', name)
        raise


def _require_new_cluster(executor, target):
    try:
        executor.run('horizondb cluster show', **target)
    except ResourceNotFoundError:
        return
    # AAZ translates HTTP errors into CLI errors; only an actual HTTP 404 permits a write.
    except Exception as ex:
        response = getattr(ex, 'response', None)
        status = getattr(response, 'status_code', None)
        if status is None:
            status = getattr(getattr(ex, 'http_response', None), 'status_code', None)
        if status != 404:
            raise
        return
    raise InvalidArgumentValueError(
        'The target Cluster already exists. az horizondb create is create-only and cannot overwrite or resume it. '
        'Use a new name, or inspect and manage the existing resources with the individual commands.')


def _public_ranges(public_access):
    if public_access is None:
        from azure.cli.command_modules.rdbms.flexible_server_virtual_network import prepare_public_network
        from knack.util import CLIError
        try:
            start, end = prepare_public_network(None, yes=True)
        except CLIError as ex:
            raise InvalidArgumentValueError(
                'Caller IPv4 discovery failed. Supply explicit --public-access IPv4 rules.') from ex
        if start != end:
            raise AzureResponseError('Caller IP discovery did not return a single IPv4 address. '
                                     'Supply explicit --public-access IPv4 rules.')
        public_access = [start]
    ranges = set()
    for item in public_access:
        try:
            if '/' in item:
                network = ipaddress.IPv4Network(item, strict=False)
                start, end = network.network_address, network.broadcast_address
            elif '-' in item:
                first, last = item.split('-', 1)
                start, end = ipaddress.IPv4Address(first), ipaddress.IPv4Address(last)
            else:
                start = end = ipaddress.IPv4Address(item)
            if start > end or start == end == ipaddress.IPv4Address('0.0.0.0'):
                raise ValueError()
        except (ValueError, TypeError) as ex:
            raise InvalidArgumentValueError(
                '--public-access requires IPv4 addresses, CIDRs, or start-end IPv4 ranges. '
                'IPv6 and the 0.0.0.0 Azure-services wildcard are not supported.') from ex
        ranges.add((str(start), str(end)))
    if not ranges:
        raise InvalidArgumentValueError('--public-access must contain at least one IPv4 rule.')
    return sorted(ranges)


def _administrator(cmd, authentication, object_id, principal_name, principal_type, tenant_id):
    if authentication == 'Password':
        if any((object_id, principal_name, principal_type, tenant_id)):
            raise InvalidArgumentValueError('Entra administrator options require Entra or Both authentication.')
        return None
    from azure.cli.core._profile import Profile
    subscription = Profile(cli_ctx=cmd.cli_ctx).get_subscription()
    if any((object_id, principal_name, principal_type)):
        if not all((object_id, principal_name, principal_type)):
            raise RequiredArgumentMissingError(
                'Supply --administrator-object-id, --administrator-principal-name, and '
                '--administrator-principal-type together.')
    else:
        from azure.cli.command_modules.role import graph_client_factory, GraphError
        from azure.cli.command_modules.role.util import get_object_id
        user = subscription['user']
        try:
            if user['type'] == 'user':
                principal = graph_client_factory(cmd.cli_ctx).signed_in_user_get()
                object_id = principal['id']
                principal_name = principal.get('userPrincipalName') or user['name']
                principal_type = 'User'
            elif user['type'] == 'servicePrincipal':
                object_id = get_object_id(cmd.cli_ctx, spn=user['name'])
                principal_type = 'ServicePrincipal'
                if object_id:
                    principal_name = graph_client_factory(cmd.cli_ctx).service_principal_get(object_id).get('displayName')
            else:
                raise RequiredArgumentMissingError(
                    'This login type requires explicit Entra administrator identifiers.')
        except GraphError as ex:
            raise AzureResponseError(
                'Entra administrator discovery failed. Supply explicit administrator identifiers and tenant ID, '
                'or grant the signed-in identity directory read permission.') from ex
        if not object_id:
            raise RequiredArgumentMissingError(
                'Unable to resolve this service connection to a tenant object ID. '
                'Supply explicit Entra administrator identifiers; an application ID is not an object ID.')
    guid(object_id)
    tenant_id = tenant_id or subscription['tenantId']
    guid(tenant_id)
    if principal_type not in ('User', 'Group', 'ServicePrincipal'):
        raise InvalidArgumentValueError('Administrator principal type must be User, Group, or ServicePrincipal.')
    if not principal_name or len(principal_name) > 256:
        raise InvalidArgumentValueError('--administrator-principal-name must contain 1-256 characters.')
    return {'object_id': object_id.lower(), 'principal_name': principal_name,
            'principal_type': principal_type, 'tenant_id': tenant_id.lower()}


def _password(authentication, login, password):
    if authentication == 'Entra':
        if login is not None or password is not None:
            raise InvalidArgumentValueError('Password credentials require --authentication Password or Both.')
        return None, None
    login = login or 'hdbadmin'
    if not 1 <= len(login) <= 63:
        raise InvalidArgumentValueError('--administrator-login must contain 1-63 characters.')
    if password is None:
        from knack.prompting import prompt_pass, NoTTYException
        try:
            password = prompt_pass('Administrator password: ', confirm=True)
        except NoTTYException as ex:
            raise RequiredArgumentMissingError(
                'Initial Password/Both setup requires --administrator-login-password or an interactive terminal.') from ex
    if not 8 <= len(password) <= 128:
        raise InvalidArgumentValueError('--administrator-login-password must contain 8-128 characters.')
    return login, password


def _regional_defaults(executor, location, version, v_cores, compute_type, compute_processor, compute_generation):
    candidates = []
    for entry in executor.capabilities(location):
        properties = _properties(entry)
        versions = properties.get('clusterCapabilities', {}).get('supportedPostgreSqlVersions', [])
        if not any(str(item.get('name')) == version for item in versions):
            continue
        for processor in properties.get('poolCapabilities', {}).get('supportedProcessors', []):
            if compute_processor is not None and processor.get('name') != compute_processor:
                continue
            for generation in processor.get('supportedGenerations', []):
                if generation.get('computeGeneration') != compute_generation:
                    continue
                for model in generation.get('supportedComputeModels', []):
                    if model.get('type') != compute_type:
                        continue
                    for size in model.get('supportedComputeSizes', []):
                        cores = size.get('vCores')
                        if isinstance(cores, int) and not isinstance(cores, bool) and (
                                v_cores is None or cores == v_cores):
                            candidates.append((cores, processor['name']))
    if not candidates:
        raise InvalidArgumentValueError(
            'The regional catalog does not advertise the requested PostgreSQL version and compute configuration. '
            'Select another location, PostgreSQL version, compute configuration, or vCore count.')
    cores, processor = min(candidates)
    bounded_int(1, 192)(cores)
    defaults = [item for item in executor.run('horizondb default-parameter-group list', location=location)
                if str(_properties(item).get('postgreSqlVersion')) == version]
    if len(defaults) != 1 or not defaults[0].get('id'):
        raise AzureResponseError('Expected one service-provided default parameter group for the selected version.')
    default_id = resource_reference(defaults[0]['id'], 'Microsoft.HorizonDb/locations/parameterGroups')
    parsed = parse_resource_id(default_id)
    if parsed.get('name', '').lower() != location.lower():
        raise AzureResponseError('The advertised default parameter group belongs to a different region.')
    actual = executor.run('horizondb default-parameter-group show', location=location,
                          name=parsed['child_name_1'])
    if str(_properties(actual).get('postgreSqlVersion')) != version:
        raise AzureResponseError('The advertised default parameter group does not match its actual version.')
    return cores, processor, default_id


def _cluster_options(data_encryption_type, primary_encryption_key_uri, primary_encryption_identity,
                     user_assigned_identities, backup_retention_days, geo_redundancy, creation_mode,
                     creation_source_cluster, creation_source_cluster_location, point_in_time, postgresql_version):
    identities = sorted(set(user_assigned_identities or []))
    for identity in identities:
        identity_reference(identity)
    if data_encryption_type not in ('SystemManaged', 'AzureKeyVault'):
        raise InvalidArgumentValueError('--data-encryption-type must be SystemManaged or AzureKeyVault.')
    if data_encryption_type == 'AzureKeyVault':
        if not primary_encryption_key_uri or not primary_encryption_identity:
            raise RequiredArgumentMissingError(
                'AzureKeyVault requires --primary-encryption-key-uri and --primary-encryption-identity.')
        key_uri(primary_encryption_key_uri)
        identity_reference(primary_encryption_identity)
        if primary_encryption_identity.lower() not in {item.lower() for item in identities}:
            raise InvalidArgumentValueError('The primary encryption identity must be attached to the Cluster.')
        if geo_redundancy == 'Enabled':
            raise InvalidArgumentValueError('AzureKeyVault encryption does not support geo-redundant backup.')
    elif primary_encryption_key_uri is not None or primary_encryption_identity is not None:
        raise InvalidArgumentValueError('Encryption key and identity options require AzureKeyVault encryption.')
    if backup_retention_days is not None:
        backup_retention_days = bounded_int(1, 35)(backup_retention_days)
        if geo_redundancy is None:
            raise RequiredArgumentMissingError('--backup-retention-days requires --geo-redundancy.')
    if geo_redundancy not in (None, 'Enabled', 'Disabled'):
        raise InvalidArgumentValueError('--geo-redundancy must be Enabled or Disabled.')
    options = {'data_encryption': {'type': data_encryption_type},
               'geo_redundancy': geo_redundancy, 'backup_retention_days': backup_retention_days}
    if data_encryption_type == 'AzureKeyVault':
        options['data_encryption'].update(primary_key_uri=primary_encryption_key_uri,
                                          primary_user_assigned_identity_id=primary_encryption_identity)
    if identities:
        options['mi_user_assigned'] = identities
    if creation_mode == 'PointInTimeRestore':
        if not creation_source_cluster or not point_in_time:
            raise RequiredArgumentMissingError(
                'PointInTimeRestore requires --creation-source-cluster and --point-in-time.')
        if postgresql_version is not None:
            raise InvalidArgumentValueError('Omit --postgresql-version for PointInTimeRestore.')
        resource_reference(creation_source_cluster, 'Microsoft.HorizonDb/clusters')
        utc_datetime(point_in_time)
        options.update(creation_source_cluster=creation_source_cluster,
                       point_in_time=datetime.fromisoformat(point_in_time.replace('Z', '+00:00')).isoformat(),
                       creation_source_cluster_location=creation_source_cluster_location)
    elif creation_mode != 'Create':
        raise InvalidArgumentValueError('--creation-mode must be Create or PointInTimeRestore.')
    elif any(value is not None for value in (creation_source_cluster, creation_source_cluster_location, point_in_time)):
        raise InvalidArgumentValueError('Restore source and time options require PointInTimeRestore.')
    return options


def _restore_version(executor, location, options):
    source_id = parse_resource_id(options['creation_source_cluster'])
    source = executor.run('horizondb cluster show', subscription=source_id['subscription'],
                          resource_group=source_id['resource_group'], name=source_id['name'])
    source_location = (source.get('location') or '').lower().replace(' ', '')
    version = _properties(source).get('postgreSqlVersion')
    supplied_location = options.get('creation_source_cluster_location')
    if supplied_location is not None and supplied_location.lower().replace(' ', '') != source_location:
        raise InvalidArgumentValueError('--creation-source-cluster-location does not match the source Cluster.')
    if supplied_location is None and source_location != location:
        raise RequiredArgumentMissingError('Cross-location restore requires --creation-source-cluster-location.')
    if not version or not source_location:
        raise AzureResponseError('The service did not return the source PostgreSQL version and location for restore.')
    options['creation_source_cluster_location'] = source_location
    return str(version)


def horizondb_create(cmd, resource_group_name, cluster_name, location=None, postgresql_version=None,
                     v_cores=None, authentication='Entra', public_access=None, enable_ai=False,
                     administrator_object_id=None, administrator_principal_name=None,
                     administrator_principal_type=None, tenant_id=None,
                     administrator_login=None, administrator_login_password=None,
                     pool_name=None, node_count=1, compute_type='Provisioned', compute_processor=None,
                     compute_generation=1, high_availability_mode='Disabled',
                     data_encryption_type='SystemManaged', primary_encryption_key_uri=None,
                     primary_encryption_identity=None, user_assigned_identities=None,
                     creation_mode='Create', creation_source_cluster=None, creation_source_cluster_location=None,
                     point_in_time=None, backup_retention_days=None, geo_redundancy=None, executor=None):
    """Provision a complete cluster only after every prerequisite has been resolved."""
    executor = executor or CommandExecutor(cmd.cli_ctx)
    dns_name(cluster_name)
    target = {'resource_group': resource_group_name, 'cluster_name': cluster_name}
    cluster_target = {'resource_group': resource_group_name, 'name': cluster_name}
    with _stage('target Cluster preflight'):
        _require_new_cluster(executor, cluster_target)
    if authentication not in ('Entra', 'Password', 'Both'):
        raise InvalidArgumentValueError('--authentication must be Entra, Password, or Both.')
    if v_cores is not None:
        v_cores = bounded_int(1, 192)(v_cores)
    pool_name = pool_name if pool_name is not None else cluster_name[:58] + '-pool'
    dns_name(pool_name)
    if pool_name == cluster_name:
        raise InvalidArgumentValueError('The Pool name must differ from the parent Cluster name.')
    node_count = bounded_int(1, 16)(node_count)
    compute_generation = bounded_int(1)(compute_generation)
    if compute_type != 'Provisioned':
        raise InvalidArgumentValueError('--compute-type must be Provisioned.')
    if high_availability_mode not in ('Disabled', 'AnyZone', 'ZoneRedundant') or (
            (node_count == 1) != (high_availability_mode == 'Disabled')):
        raise InvalidArgumentValueError(
            'One Node requires Disabled high availability; 2-16 Nodes require AnyZone or ZoneRedundant.')
    options = _cluster_options(
        data_encryption_type, primary_encryption_key_uri, primary_encryption_identity, user_assigned_identities,
        backup_retention_days, geo_redundancy, creation_mode, creation_source_cluster,
        creation_source_cluster_location, point_in_time, postgresql_version)
    with _stage('resource group and prerequisite discovery'):
        group = executor.resource_group(resource_group_name)
        location = (location or group['location']).lower().replace(' ', '')
        ranges = _public_ranges(public_access)
        administrator = _administrator(cmd, authentication, administrator_object_id, administrator_principal_name,
                                       administrator_principal_type, tenant_id)
        login, password = _password(authentication, administrator_login, administrator_login_password)
        version = (_restore_version(executor, location, options) if creation_mode == 'PointInTimeRestore'
                   else str(postgresql_version or '17'))
        cores, processor, default = _regional_defaults(
            executor, location, version, v_cores, compute_type, compute_processor, compute_generation)
    password_state = 'Enabled' if authentication in ('Password', 'Both') else 'Disabled'
    entra_state = 'Enabled' if authentication in ('Entra', 'Both') else 'Disabled'
    ai = 'Enabled' if enable_ai else 'Disabled'
    with _stage('cluster creation'):
        _require_new_cluster(executor, cluster_target)
        command = 'horizondb cluster restore' if creation_mode == 'PointInTimeRestore' else 'horizondb cluster create'
        executor.run(command, **cluster_target, location=location, public_access='Enabled',
                     postgresql_version=version if creation_mode == 'Create' else None, **options)
    with _stage('pool creation'):
        pool = executor.run(
            'horizondb cluster pool create', **target, name=pool_name, compute_generation=compute_generation,
            compute_processor=processor, v_cores=cores, node_count=node_count,
            high_availability_mode=high_availability_mode, parameter_group=default,
            parameter_apply_method='Immediate')
    with _stage('authentication configuration'):
        if password_state == 'Enabled':
            executor.run('horizondb cluster authentication password create', **target, state=password_state,
                         administrator_login=login, administrator_login_password=password)
        executor.run('horizondb cluster authentication microsoft-entra create', **target, state=entra_state)
        if administrator:
            executor.run('horizondb cluster microsoft-entra-administrator create', **target, **administrator)
        if password_state == 'Disabled':
            executor.run('horizondb cluster authentication password create', **target, state=password_state)
    with _stage('authentication confirmation'):
        actual_password = executor.run('horizondb cluster authentication password show', **target)
        actual_entra = executor.run('horizondb cluster authentication microsoft-entra show', **target)
        if _properties(actual_password).get('state') != password_state or _properties(actual_entra).get('state') != entra_state:
            raise AzureResponseError('The service did not confirm the requested authentication state. '
                                     'Resources were retained; inspect authentication show for manual recovery.')
    with _stage('firewall configuration'):
        for index, (start, end) in enumerate(ranges, 1):
            executor.run('horizondb cluster pool firewall-rule create', **target, pool_name=pool_name,
                         name=f'cli-create-{index}', start_ip_address=start, end_ip_address=end)
    with _stage('AI configuration'):
        executor.run('horizondb cluster update', **cluster_target, ai_model_management=ai)
    with _stage('connection discovery'):
        cluster = executor.run('horizondb cluster show', **cluster_target)
        if _properties(cluster).get('aiModelManagement') != ai:
            raise AzureResponseError('The service did not confirm the requested AI Model Management state after PATCH. '
                                     'Resources were retained; inspect cluster show for manual recovery.')
        endpoints = executor.run('horizondb cluster endpoint list', **target)
        if not any(_properties(endpoint).get('scope') == 'Cluster' and
                   _properties(endpoint).get('role') == 'ReadWrite' and
                   _properties(endpoint).get('fullyQualifiedDomainName') for endpoint in endpoints):
            raise AzureResponseError('The service has not returned a usable read-write Cluster endpoint. '
                                     'Resources were retained; inspect endpoint list for manual recovery.')
    properties = _properties(cluster)
    return {
        'cluster': {'id': cluster.get('id'), 'name': cluster_name, 'location': location,
                    'postgresqlVersion': version, 'dataEncryption': properties.get('dataEncryption'),
                    'backup': properties.get('backup'), 'creationMode': properties.get('creationMode', 'Create'),
                    'identity': cluster.get('identity'),
                    **{key: properties[key] for key in ('creationSourceClusterResourceId',
                                                        'creationSourceClusterLocation', 'pointInTimeUtc')
                       if key in properties}},
        'pool': {'id': pool.get('id'), 'name': pool_name, 'vCores': cores, 'nodeCount': node_count,
                 'computeModel': _properties(pool).get('computeModel'),
                 'highAvailability': _properties(pool).get('highAvailability')},
        'connection': {'authentication': authentication, 'sslMode': 'require',
                       'endpoints': [{'id': endpoint.get('id'),
                                      'host': _properties(endpoint).get('fullyQualifiedDomainName'),
                                      'scope': _properties(endpoint).get('scope'),
                                      'role': _properties(endpoint).get('role')} for endpoint in endpoints]},
        'firewall': [{'startIpAddress': start, 'endIpAddress': end} for start, end in ranges],
        'aiModelManagement': ai,
    }
