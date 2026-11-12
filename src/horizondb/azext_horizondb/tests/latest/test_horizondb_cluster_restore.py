# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
from datetime import datetime, timedelta, timezone
from time import sleep

from azure.cli.testsdk import KeyVaultPreparer, NoneCheck, ResourceGroupPreparer, ScenarioTest
from azure.cli.testsdk.scenario_tests import AllowLargeResponse
from azure.cli.testsdk.scenario_tests.const import ENV_LIVE_TEST

from .constants import INDIASOUTHCENTRAL, CLUSTER_NAME_PREFIX, CLUSTER_NAME_MAX_LENGTH


class HorizonDBClusterRestoreCommandScenarioTest(ScenarioTest):

    @AllowLargeResponse()
    @ResourceGroupPreparer(name_prefix='cli_test_horizondb_restore_', location=INDIASOUTHCENTRAL)
    @KeyVaultPreparer(name_prefix='horizonvault', parameter_name='vault_name', location=INDIASOUTHCENTRAL,
                      additional_params='--enable-purge-protection true --retention-days 7 --no-self-perms')
    def test_horizondb_cluster_restore_command(self, resource_group, vault_name):
        self.kwargs.update({
            'rg': resource_group,
            'location': INDIASOUTHCENTRAL,
            'vault_name': vault_name,
            'vault_scope': (
                '/subscriptions/{}/resourceGroups/{}/providers/Microsoft.KeyVault/vaults/{}'.format(
                    self.get_subscription_id(), resource_group, vault_name)
            ),
            'key_name': self.create_random_name('horizonkey', 32),
            'cluster': self.create_random_name(CLUSTER_NAME_PREFIX, CLUSTER_NAME_MAX_LENGTH),
            'restored_cluster': self.create_random_name(CLUSTER_NAME_PREFIX, CLUSTER_NAME_MAX_LENGTH),
            'pool': self.create_random_name('pool-', 24),
        })
        key = self.cmd(
            'keyvault key create --name {key_name} -p software --vault-name {vault_name}',
        ).get_output_in_json()
        self.kwargs['key_uri'] = key['key']['kid'].rsplit('/', 1)[0]
        for purpose in ['source', 'restore']:
            self.kwargs['identity_name'] = self.create_random_name('identity', 32)
            identity = self.cmd(
                'identity create -g {rg} --name {identity_name} --location {location}',
            ).get_output_in_json()
            self.kwargs[purpose + '_identity_id'] = identity['id']
            if self.is_live:
                self.kwargs['identity_principal_id'] = identity['principalId']
                self.cmd(
                    'role assignment create --assignee-object-id {identity_principal_id} '
                    '--assignee-principal-type ServicePrincipal --role "Key Vault Crypto User" --scope {vault_scope}',
                )
        if self.is_live:
            # Key Vault RBAC assignments need time to propagate before cluster creation.
            sleep(60)

        source = self.cmd(
            'horizondb cluster create -g {rg} -n {cluster} --location {location} '
            '--version 17 --geo-redundancy Disabled --public-access Disabled --tags scenario=source '
            '--primary-key-uri {key_uri} --primary-user-assigned-identity-id {source_identity_id}',
            checks=[
                self.check('name', '{cluster}'),
                self.check('properties.provisioningState', 'Succeeded'),
                self.check('properties.dataEncryption.type', 'AzureKeyVault'),
                self.check('properties.dataEncryption.primaryKeyUri', '{key_uri}'),
                self.check('properties.dataEncryption.primaryUserAssignedIdentityId', '{source_identity_id}'),
                self.check('identity.type', 'UserAssigned'),
                self.check("contains(keys(identity.userAssignedIdentities), '{source_identity_id}')", True),
            ],
        ).get_output_in_json()
        self.kwargs['source_id'] = source['id']

        self.cmd(
            'horizondb cluster pool create -g {rg} --cluster-name {cluster} -n {pool} '
            '--compute-generation 1 --compute-processor Intel --v-cores 2 '
            '--node-count 1 --high-availability-mode Disabled',
        )
        # Wait until snapshot is created
        os.environ.get(ENV_LIVE_TEST, False) and sleep(1800)
        source = self.cmd('horizondb cluster show -g {rg} -n {cluster}').get_output_in_json()
        self.kwargs['restore_time'] = (
            (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace('+00:00', 'Z')
        )

        self.cmd(
            'horizondb cluster restore -g {rg} -n {restored_cluster} '
            '--source-cluster-id {source_id} --point-in-time-utc {restore_time} --tags scenario=restored '
            '--primary-key-uri {key_uri} --primary-user-assigned-identity-id {restore_identity_id}',
            checks=[
                self.check('name', '{restored_cluster}'),
                self.check('location', '{location}'),
                self.check('properties.creationMode', 'PointInTimeRestore'),
                self.check('properties.postgreSqlVersion', '17'),
                self.check('properties.backup.geoRedundancy', 'Disabled'),
                self.check('tags.scenario', 'restored'),
                self.check('properties.dataEncryption.type', 'AzureKeyVault'),
                self.check('properties.dataEncryption.primaryKeyUri', '{key_uri}'),
                self.check('properties.dataEncryption.primaryUserAssignedIdentityId', '{restore_identity_id}'),
                self.check('identity.type', 'UserAssigned'),
                self.check("contains(keys(identity.userAssignedIdentities), '{source_identity_id}')", True),
                self.check("contains(keys(identity.userAssignedIdentities), '{restore_identity_id}')", True),
            ],
        )

        self.cmd('horizondb cluster delete -g {rg} -n {restored_cluster} --yes', checks=NoneCheck())
        self.cmd(
            'horizondb cluster pool delete -g {rg} --cluster-name {cluster} -n {pool} --yes',
            checks=NoneCheck(),
        )
        self.cmd('horizondb cluster delete -g {rg} -n {cluster} --yes', checks=NoneCheck())
