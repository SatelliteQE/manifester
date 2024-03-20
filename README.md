# Manifester

Red Hat subscriptions made manifest.

# Description
Manifester is a tool that uses the Red Hat Subscription Management (RHSM) API to dynamically create and populate subscription allocations and to export subscription manifests for use by Red Hat Satellite and other Red Hat products.
# Installation

Clone this repository:
```
git clone https://github.com/SatelliteQE/manifester
```
Copy and rename the `manifester_settings.yaml.example` file to `manifester_settings.yaml`.

An offline token is required to generate an offline token the temporary access tokens used for authenticating to the RHSM API. Either use an existing offline token for an RHSM account or generate one using the instructions in the article [Getting started with Red Hat APIs](https://access.redhat.com/articles/3626371#bgenerating-a-new-offline-tokenb-3). Add the offline token to `manifester_settings.yaml`.

From the base directory of the local clone of the manifest repository, install the project to a local Python environment:
```
pip install .
```
# Configuration

The `manifester_settings.yaml` file is used to configure manifester via [DynaConf](https://github.com/rochacbruno/dynaconf/).

Multiple types of manifests can be configured in the `manifest_category` section of `manifester_settings.yaml`. These types can be differentiated based on the Satellite version of the subscription allocation, the names and quantities of the subscriptions to be added to the manifest, and whether [Simple Content Access](https://access.redhat.com/documentation/en-us/subscription_central/2021/html-single/getting_started_with_simple_content_access/index) is enabled on the manifest.

The value of the `name` setting for each subscription in a manifest must exactly match the name of a subscription available in the account which was used to generate the offline token. One method for determining the subscription names available in an account is to register a system to RHSM and then run `subscription manager list --available` on that system. A planned future feature of Manifester is a CLI command that will return a list of available subscriptions.

# CLI Usage

Currently, the manifester CLI supports three subcommands: `get-manifest`, `delete`, and `inventory`.

The `get-manifest` subcommand is used to generate a manifest that is saved to the `./manifests` directory. Two options are supported for this command. `--manifest-category` is required, and the value passed to it **must** be defined as a manifest category in the `manifester_settings.yaml` configuration file. The `--allocation-name` option is optional and can be used to specify the name of the subscription allocation in RHSM, which will subsequently form part of the generated manifest's filename. If novalue is supplied for `--allocation_name`, a string of 10 random alphabetic characters will be joined to the value of the `username_prefix` setting in `manifester_settings.yaml`. A third option, `--requester`, is intended for future integration with Manifester's unit tests but is not currently supported. Example usage:
```
$ manifester get-manifest --manifest-category <manifest category name> --allocation-name <allocation name>
```
The `inventory` subcommand is used to display the contents of the local inventory file, the location of which is specified by the `inventory_path` setting in `manifester_settings.yaml`. Executing `manifester inventory` without options will write a a table to standard output that contains the name of each subscription allocation created by the user and an inventory index number for each allocation. Passing the `--details` option will print additional details about the allocation returned by the RHSM API. Passing the `--sync` option will update the inventory from the RHSM API before printing the inventory. **NOTE:** The inventory is generated based on the subscription allocations in the RHSM account with names beginning with the `username_prefix` defined in `manifester_settings.yaml`. Maintaining a unique and consistent `username_prefix` (such as the user's RHSM account username) is therefore crucial to accurate inventory management. Example usage and output:
```
$ manifester inventory
[I 240320 14:52:02 commands:78] Displaying local inventory data
--------------------------------------
| Index | Allocation Name            |
--------------------------------------
| 0     | user-mBIojPMF              |
--------------------------------------
$ manifester inventory --details
[I 240320 14:52:42 commands:86] Displaying detailed local inventory data
0:
    entitlementQuantity: 4
    name: user-mBIojPMF
    simpleContentAccess: enabled
    type: Satellite
    url: https://api.access.redhat.com/management/v1/allocations/2ea75142-8ea4-46db-87e3-1feab8613000
    uuid: 2ef73132-83a4-473b-97e3-1feab8623000
    version: 6.14
```
The `delete` subcommand will delete subscription allocations in the inventory from RHSM and, optionally, the local manifest file associated with those allocations. The `delete` subcommand will accept either a list of inventory index numbers or a list of subscription allocation names. Alternatively, the `--all` option will delete all subscription allocations in the inventory. Passing the `--remove-manifest-file` option will cause the CLI to delete the manifest files of any deleted subscription allocations from the local file system in addition to deleting the subscription allocation in RHSM. Example usage:
```
$ manifester delete 0 1 2
$ manifester delete user-mBIojPMF
$ manifester delete --all
```
