# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Generate HorizonDB AAZ models and CLI commands with aaz-dev 4.7.2."""

import argparse
from importlib.metadata import version
from pathlib import Path

import aaz_dev  # noqa: F401
from cli.api._cmds import _build_profile
from cli.controller.az_module_manager import AzExtensionManager
from command.controller.workspace_manager import WorkspaceManager
from command.model.configuration import CMDCommand, CMDSchemaDefault
from swagger.controller.specs_manager import SwaggerSpecsManager
from swagger.utils.source import SourceTypeEnum
from utils.config import Config
from command_help import update_help


API_VERSION = "2026-10-01-preview"


def set_constant(editor, command, variable, value):
    schemas = list(editor.iter_schema_in_command_by_arg_var(command, variable))
    if not schemas:
        raise RuntimeError(f"No request schema found for {variable}.")
    for _, schema, _ in schemas:
        schema.const = True
        schema.default = CMDSchemaDefault({"value": value})
        schema.arg = None
    command.generate_args()
    editor.reformat()


def remove_request_property(editor, command, variable):
    schemas = list(editor.iter_schema_in_command_by_arg_var(command, variable))
    if not schemas:
        raise RuntimeError(f"No request schema found for {variable}.")
    for parent, schema, _ in schemas:
        parent.props.remove(schema)
    command.generate_args()


def clear_request_default(editor, command, variable):
    schemas = list(editor.iter_schema_in_command_by_arg_var(command, variable))
    if not schemas:
        raise RuntimeError(f"No request schema found for {variable}.")
    for _, schema, _ in schemas:
        schema.default = None
    argument, _ = editor.find_arg_by_var("horizondb", "cluster", command.name, arg_var=variable)
    if argument is None:
        raise RuntimeError(f"No generated argument found for {variable}.")
    argument.default = None


def require_request_properties(editor, command, *variables):
    for variable in variables:
        schemas = list(editor.iter_schema_in_command_by_arg_var(command, variable))
        if not schemas:
            raise RuntimeError(f"No request schema found for {variable}.")
        for _, schema, _ in schemas:
            schema.required = True
    command.generate_args()
    for variable in variables:
        argument, _ = editor.find_arg_by_var("horizondb", "cluster", command.name, arg_var=variable)
        if argument is None:
            raise RuntimeError(f"No generated argument found for {variable}.")
        argument.required = True


def split_cluster_creation(workspace):
    names = ["horizondb", "cluster"]
    leaf = workspace.find_command_tree_leaf(*names, "create")
    editor = workspace.load_cfg_editor_by_command(leaf)
    create = editor.find_command(*leaf.names)
    workspace._unset_cfg_editor(editor)
    # A client retention default would send backup without its required geoRedundancy.
    # Omit the backup object unless requested and let the service apply its default.
    clear_request_default(editor, create, "$resource.properties.backup.retentionDays")
    restore = CMDCommand(create.to_native())
    restore.name = "restore"
    restore.description = "Restore a HorizonDB cluster from backup."
    editor._add_command(*names, "restore", command=restore)
    root = "$resource.properties."
    for suffix in ("creationSourceClusterLocation", "creationSourceClusterResourceId", "pointInTimeUtc"):
        remove_request_property(editor, create, root + suffix)
    remove_request_property(editor, restore, root + "postgreSqlVersion")
    create.description = "Create a HorizonDB cluster."
    set_constant(editor, create, root + "creationMode", "Create")
    set_constant(editor, restore, root + "creationMode", "PointInTimeRestore")
    require_request_properties(editor, create, root + "postgreSqlVersion")
    require_request_properties(editor, restore, root + "creationSourceClusterResourceId", root + "pointInTimeUtc")
    editor.reformat()
    workspace._set_cfg_editor(editor)


def configure_private_endpoint_actions(workspace):
    private_endpoint = ["horizondb", "cluster", "private-endpoint-connection"]
    leaf = workspace.find_command_tree_leaf(*private_endpoint, "create")
    editor = workspace.load_cfg_editor_by_command(leaf)
    original = editor.find_command(*leaf.names)
    workspace._unset_cfg_editor(editor)
    for action, status in (("approve", "Approved"), ("reject", "Rejected")):
        command = CMDCommand(original.to_native())
        command.name = action
        command.description = f"{action.capitalize()} an existing HorizonDB private endpoint connection."
        editor._add_command(*private_endpoint, action, command=command)
        state = next(arg for group in command.arg_groups for arg in group.args
                     if "private-link-service-connection-state" in arg.options)
        variable = state.var
        editor.flatten_arg(*private_endpoint, action, arg_var=variable)
        set_constant(editor, command, variable + ".status", status)
    # Clone both actions before removing their source. Keep all read/delete
    # commands so generation also retains the group's supported wait command.
    for action in ("create", "update"):
        editor._remove_command(*private_endpoint, action)
    editor.reformat()
    workspace._set_cfg_editor(editor)


def configure_argument_names(workspace):
    property_options = {
        "version": ["postgresql-version"],
        "parameter-group-resource-id": ["parameter-group"],
        "parameter-group-apply-method": ["parameter-apply-method"],
        "creation-source-cluster-resource-id": ["creation-source-cluster"],
        "point-in-time-utc": ["point-in-time"],
        "destination-resource-id": ["destination"],
        "identity-assignment-resource-id": ["identity-assignment"],
        "identity-resource-id": ["identity"],
    }
    resource_selectors = {
        ("horizondb", "cluster"): "cluster-name",
        ("horizondb", "cluster", "pool"): "pool-name",
        ("horizondb", "cluster", "change-data-capture-destination"): "destination-name",
        ("horizondb", "parameter-group", "connection"): "parameter-group-name",
    }
    for leaf in workspace.iter_command_tree_leaves():
        names = tuple(leaf.names)
        editor = workspace.load_cfg_editor_by_command(leaf)
        command = editor.find_command(*names)
        selector = resource_selectors.get(names[:-1])
        for group in command.arg_groups:
            for argument in group.args:
                options = set(argument.options)
                if "object-id" in options:
                    argument.options = ["object-id"]
                elif "name" in options or selector in options:
                    argument.options = ["name", "n"]
                elif names[:-1] == ("horizondb", "cluster") and "retention-days" in options:
                    argument.options = ["backup-retention-days"]
                elif names[:-2] == ("horizondb", "cluster", "authentication") \
                        and "administrator-login-password" in options:
                    argument.options = ["administrator-login-password", "p"]
                else:
                    for option, replacement in property_options.items():
                        if option in options:
                            argument.options = replacement
                            break
        editor.reformat()


def generate(specs, aaz, extensions):
    if version("aaz-dev") != "4.7.2":
        raise RuntimeError("HorizonDB generation requires aaz-dev==4.7.2.")
    Config.SWAGGER_PATH = str(specs.resolve())
    Config.AAZ_PATH = str(aaz.resolve())
    Config.CLI_EXTENSION_PATH = str(extensions.resolve())
    manager = SwaggerSpecsManager()
    module = manager.get_module_manager("mgmt-plane", "horizondb")
    provider = module.get_openapi_resource_provider("Microsoft.HorizonDb")
    resources = provider.get_resource_map_by_tag("package-horizondb-" + API_VERSION)
    resources = {resource: versions for resource, versions in resources.items()
                 if resource.lower() != "/providers/microsoft.horizondb/operations"
                 # Withhold log APIs (HTTP 501), including collection/action paths.
                 and not {"logcaptureconfigurations", "logfiles"}.intersection(resource.lower().split("/"))}
    if not resources:
        raise RuntimeError("The HorizonDB OpenAPI tag does not contain resources.")
    workspace = WorkspaceManager.new(
        "horizondb", plane="mgmt-plane", mod_names="horizondb",
        resource_provider="Microsoft.HorizonDb", source=SourceTypeEnum.OpenAPI,
        folder=WorkspaceManager.IN_MEMORY, swagger_manager=manager,
    )

    def add(selected):
        workspace.add_new_resources_by_swagger(
            mod_names="horizondb", version=API_VERSION,
            resources=[
                {"id": resource, "options": (
                    {"update_by": "PatchOnly"}
                    if "patch" in versions[API_VERSION].operations.values() else {})}
                for resource, versions in selected.items()
            ],
        )

    defaults = {resource: versions for resource, versions in resources.items()
                if "/locations/" in resource and "/parametergroups" in resource}
    add(defaults)
    workspace.rename_command_tree_node(
        "horizon-db", "parameter-group",
        new_node_names=["horizon-db", "default-parameter-group"],
    )
    add({resource: versions for resource, versions in resources.items()
         if resource not in defaults and "/maintenanceevents" not in resource})
    workspace.rename_command_tree_node("horizon-db", new_node_names=["horizondb"])
    workspace.rename_command_tree_node(
        "horizondb", "cluster", "authentication", "password-method",
        new_node_names=["horizondb", "cluster", "authentication", "password"],
    )
    for leaf in list(workspace.iter_command_tree_leaves()):
        names = list(leaf.names)
        if names[:4] == ["horizondb", "cluster", "change-data-capture", "default"]:
            workspace.rename_command_tree_leaf(*names, new_leaf_names=names[:3] + names[4:])
    for leaf in workspace.iter_command_tree_leaves():
        names = list(leaf.names)
        if names[-1] not in ("create", "update"):
            continue
        editor = workspace.load_cfg_editor_by_command(leaf)
        command = editor.find_command(*names)
        root = "$resource" if names[-1] == "create" else "$properties"
        if names[:-1] == ["horizondb", "cluster"]:
            for suffix in ("backup", "network"):
                editor.flatten_arg(*names, arg_var=root + ".properties." + suffix)
        if names[:-1] in (["horizondb", "cluster"], ["horizondb", "parameter-group"]):
            editor.update_arg_by_var(
                *names, arg_var=root + ".properties.postgreSqlVersion",
                options=["version"],
            )
        if names[:-1] == ["horizondb", "cluster", "pool"]:
            for suffix, options in {
                    "computeModel": {"type": ["compute-model-type"]},
                    "highAvailability": {"mode": ["high-availability-mode"]},
                    "parameterGroup": {"applyMethod": ["parameter-group-apply-method"]}}.items():
                variable = root + ".properties." + suffix
                editor.flatten_arg(
                    *names, arg_var=variable,
                    sub_args_options={variable + "." + key: value for key, value in options.items()},
                )
            if names[-1] == "create":
                set_constant(editor, command, root + ".properties.computeModel.type", "Provisioned")
            else:
                editor.update_arg_by_var(*names, arg_var=root + ".properties.computeModel.type", hide=True)
            editor.update_arg_by_var(*names, arg_var=root + ".properties.scheduledMaintenance", hide=True)
        command.generate_args()
        editor.reformat()
    split_cluster_creation(workspace)
    configure_private_endpoint_actions(workspace)
    configure_argument_names(workspace)
    workspace.update_command_tree_node_stage("horizondb", stage="Preview")
    workspace.generate_to_aaz()

    commands = {}
    for leaf in workspace.iter_command_tree_leaves():
        names = tuple(leaf.names)
        if names[:3] == ("horizondb", "cluster", "identity"):
            continue
        if names[-1] == "update" and names[-2] in ("microsoft-entra-administrator", "identity-assignment"):
            continue
        commands[names] = leaf.version
    profile = _build_profile("latest", commands)
    profile.command_groups["horizondb"].command_groups["capability"].commands["list"].registered = False
    capability_default = profile.command_groups["horizondb"].command_groups["capability"].command_groups["default"]
    capability_default.commands["show"].registered = False
    extension_manager = AzExtensionManager()
    extension_manager.update_module("horizondb", {"latest": profile})
    update_help(extensions / "src" / "horizondb")
    print(f"Generated {len(commands)} operation commands, plus supported wait commands.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", type=Path, required=True, help="azure-rest-api-specs checkout")
    parser.add_argument("--aaz", type=Path, required=True, help="AAZ definitions checkout for generated models")
    parser.add_argument("--extensions", type=Path, default=Path(__file__).resolve().parents[3])
    arguments = parser.parse_args()
    generate(arguments.specs, arguments.aaz, arguments.extensions)
