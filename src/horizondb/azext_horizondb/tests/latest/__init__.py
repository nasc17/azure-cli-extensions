# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------


def load_commands(cli_ctx):
    from azext_horizondb import HorizonDBCommandsLoader

    cli_ctx.invocation = cli_ctx.invocation_cls(
        cli_ctx=cli_ctx, parser_cls=cli_ctx.parser_cls,
        commands_loader_cls=cli_ctx.commands_loader_cls, help_cls=cli_ctx.help_cls,
    )
    cli_ctx.invocation.data['command_string'] = ''
    loader = HorizonDBCommandsLoader(cli_ctx=cli_ctx)
    commands = loader.load_command_table(None)
    master = cli_ctx.invocation.commands_loader
    master.command_table.update(commands)
    master.cmd_to_loader_map.update({name: [loader] for name in commands})
    master.load_arguments()
    for command in commands.values():
        command.command_source = None
    return loader
