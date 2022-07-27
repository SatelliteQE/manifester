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

Currently, the only action supported by the manifester CLI is generating a manifest using the `get-manifest` subcommand:
```
manifester get-manifest --manifest-category <manifest category name> --allocation_name <allocation name>
```
 Two options are available for this subcommand. The `--manifest_category` option is required and must match one of the manifest categories defined in `manifester_settings.yaml`. The `--allocation_name` option specifies the name of the subscription allocation in RHSM and is also used in the file name of the manifest archive exported by Manifester. If no value is supplied for `--allocation_name`, a string of 10 random alphabetic characters will be used for the allocation name.
