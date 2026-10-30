.. :changelog:

Release History
===============

1.0.0b9
+++++++
* New api version.
* Keep `az horizondb cluster create` scoped to the Create Cluster API, without pool creation or pool arguments, and support `--no-wait`.
* Generate separate cluster create and restore commands with implicit creation modes and mode-specific required arguments.
* Leave omitted backup settings to service defaults instead of sending retention without the required geo-redundancy setting.
* Reserve complete pool, authentication, network, encryption, and prerequisite setup for `az horizondb create`.
* Register root convenience creation as a standard custom command with conventional arguments and help, while retaining generated AAZ resource operations.
* Expand the nested AAZ command surface to cover 88 SDK-based resource commands while retaining three redesign commands.
* Generate from the corrected 2026-10-01-preview API contracts, including asynchronous PUT creation, restore inputs, Pool properties, and firewall rules.
* Add AAZ-backed convenience creation, authentication, change data capture, logs, nodes, endpoints, and default parameter groups.
* Add reproducible AAZ generation tooling and offline command coverage and request-contract tests.
* Restore 111 resource help examples in the nested hierarchy, retain the two redesign examples, and document its three extra commands.
* Generate original SDK-based argument names without redesign compatibility aliases, retaining AAZ structured inputs and reproducible per-command help.
* Use action-specific short and long help, self-contained sample values, and redacted passwords in examples.
* Use zero-initialized GUIDs for all example subscription, tenant, principal, and workspace IDs.
* Put concise command summaries in short help and detailed API behavior in long help.
* Expose explicit default parameter-group selection on pool creation and restore null-patch identity removal on cluster update.
* Keep Capabilities internal and exclude provider Operations from public commands and help groups.
* Withhold the log capture configuration and log file command groups until their backend APIs are implemented.
* Use only private endpoint connection `approve` and `reject` for state changes; remove redundant public `create` and `update` commands while retaining `show`, `list`, `delete`, and `wait`.

1.0.0b8
+++++++
* Add support for restoring HorizonDB clusters through `az horizondb restore`.

1.0.0b7
+++++++
* Add `az horizondb parameter-group` commands to create, delete, list, show, and list connections for HorizonDB parameter groups.

1.0.0b6
+++++++
* Add private endpoint connection commands: `az horizondb private-endpoint-connection list/show/approve/reject/delete`.
* Add private link resource commands: `az horizondb private-link-resource list/show`.

1.0.0b5
+++++++
* Add support for configuring public access on HorizonDB clusters through `az horizondb create --public-access` and `az horizondb update --public-access`. Supplying an IP address or range automatically creates a firewall rule.
* Add the `az horizondb firewall-rule` command group (`create`, `show`, `list`, `update`, `delete`) to manage cluster firewall rules.

1.0.0b4
+++++++
* Update validation checks for commands. Add short form arguments for user convenience.

1.0.0b3
+++++++
* Add support for assigning a parameter group to HorizonDB clusters through `az horizondb update --parameter-group`.

1.0.0b2
+++++++
* Add support for updating HorizonDB clusters through `az horizondb update`.

1.0.0b1
+++++++
* Add create, list, and delete commands for HorizonDB clusters.

0.1.0
++++++
* Initial release.
