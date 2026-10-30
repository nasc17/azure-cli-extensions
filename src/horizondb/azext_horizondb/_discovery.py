# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Read regional capabilities using the private, generated AAZ operation.

The generated class is deliberately not a public CLI command. Keep the import local so
ordinary nested commands do not load this root-workflow-only prerequisite.
"""

from importlib import import_module


def list_regional_capabilities(cli_ctx, location):
    """Return all advertised capabilities without consulting the public command table."""
    module = import_module('.aaz.latest.horizondb.capability._list', __package__)
    return list(module.List(cli_ctx=cli_ctx)({'location': location}))
