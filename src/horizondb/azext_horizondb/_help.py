# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.help_files import helps


helps['horizondb create'] = """
type: command
short-summary: Create a fully configured HorizonDB cluster.
long-summary: |
  Create-only: existing clusters, including partial deployments, are rejected. Waits for every setup stage;
  --no-wait is not supported. Defaults to signed-in Entra authentication and the detected caller IPv4. Explicit
  --public-access ranges bypass IP discovery. Resources are retained on failure. Credentials and tokens are
  never returned. Do not use --debug with credentials: expanded arguments may appear in CLI debug logs.
examples:
  - name: Create a cluster with Entra authentication.
    text: |
      az horizondb create -g example-rg -n example-cluster
  - name: Create a cluster with public access and AI enabled.
    text: |
      az horizondb create -g example-rg -n example-cluster --location indonesiacentral --public-access 203.0.113.10
      198.51.100.0/28 --enable-ai
  - name: Create a cluster with Entra and password authentication.
    text: |
      az horizondb create -g example-rg -n example-cluster --authentication Both --administrator-login hdbadmin
      --public-access 203.0.113.10
  - name: Create a cluster with a three-node pool.
    text: |
      az horizondb create -g example-rg -n example-cluster --pool-name primary --node-count 3 --compute-processor
      Intel --v-cores 8 --high-availability-mode ZoneRedundant --backup-retention-days 14 --geo-redundancy Enabled
      --public-access 203.0.113.10
  - name: Create a cluster with a customer-managed key.
    text: |
      az horizondb create -g example-rg -n example-cluster --data-encryption-type AzureKeyVault
      --primary-encryption-key-uri https://example-vault.vault.azure.net/keys/example-key
      --primary-encryption-identity
      "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example-rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/example-identity"
      --user-assigned-identities
      "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example-rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/example-identity"
      --geo-redundancy Disabled --public-access 203.0.113.10
  - name: Restore a cluster.
    text: |
      az horizondb create -g example-rg --name restored-cluster --location eastus2 --creation-mode PointInTimeRestore
      --creation-source-cluster
      "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example-rg/providers/Microsoft.HorizonDb/clusters/source-cluster"
      --point-in-time 2026-10-01T12:00:00Z --pool-name restored-pool --public-access 203.0.113.10
"""
