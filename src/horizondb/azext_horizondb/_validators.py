# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Validation shared by the root create workflow (independent of an SDK)."""

from datetime import datetime
import re
import uuid
from urllib.parse import urlparse

from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.mgmt.core.tools import is_valid_resource_id, parse_resource_id


def dns_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
        raise InvalidArgumentValueError('Names must be lowercase DNS labels of 1-63 characters.')
    return value


def bounded_int(minimum, maximum=None):
    def parse(value):
        try:
            number = int(value)
        except (ValueError, TypeError) as ex:
            raise InvalidArgumentValueError('Expected an integer.') from ex
        if number < minimum or (maximum is not None and number > maximum):
            raise InvalidArgumentValueError(
                f'Expected an integer in the range {minimum}-{maximum if maximum is not None else "unbounded"}.')
        return number
    return parse


def guid(value):
    try:
        if str(uuid.UUID(value)).lower() != value.lower():
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as ex:
        raise InvalidArgumentValueError('Expected a GUID in xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx format.') from ex
    return value


def utc_datetime(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)', value):
            raise ValueError()
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError) as ex:
        raise InvalidArgumentValueError('Expected an RFC 3339 UTC date-time, for example 2026-10-01T12:00:00Z.') from ex
    return value


def resource_reference(value, resource_type=None):
    if not is_valid_resource_id(value):
        raise InvalidArgumentValueError('Expected a complete ARM resource ID.')
    parsed = parse_resource_id(value)
    if not all(parsed.get(key) for key in ('subscription', 'namespace', 'type', 'name')):
        raise InvalidArgumentValueError('Expected a complete ARM resource ID.')
    actual = parsed['namespace'] + '/' + parsed['type']
    for key in ('child_type_1', 'child_type_2', 'child_type_3'):
        if parsed.get(key):
            actual += '/' + parsed[key]
    if resource_type and actual.lower() != resource_type.lower():
        raise InvalidArgumentValueError(f'Expected a {resource_type} resource ID.')
    return value


def identity_reference(value):
    return resource_reference(value, 'Microsoft.ManagedIdentity/userAssignedIdentities')


def key_uri(value):
    parsed = urlparse(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or
            parsed.password is not None or parsed.query or parsed.fragment or
            not re.fullmatch(r'/keys/[^/]+/?', parsed.path)):
        raise InvalidArgumentValueError(
            'Use a versionless HTTPS Azure Key Vault key URI: https://<vault>/keys/<key>.')
    return value
