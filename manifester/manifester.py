"""Main interface for the RHSM API.

This module defines the `Manifester` class, which provides methods for authenticating to and
interacting with the RHSM Subscription API for the purpose of generating a subscription manifest.
"""
from functools import cached_property
from pathlib import Path
import random
import string

from dynaconf.utils.boxing import DynaBox
from requests.exceptions import RequestException, Timeout

from manifester.helpers import (
    fetch_paginated_data,
    process_sat_version,
    simple_retry,
    update_inventory,
)
from manifester.logger import _logger as logger
from manifester.settings import settings


class Manifester:
    """Main Manifester class responsible for generating a manifest from the provided settings."""

    def __init__(
        self,
        manifest_category=None,
        allocation_name=None,
        minimal_init=False,
        proxies=None,
        **kwargs,
    ):
        if minimal_init:
            if kwargs.get("offline_token") is not None:
                self.offline_token = kwargs.get("offline_token")
            elif settings.get("offline_token") is not None:
                self.offline_token = settings.get("offline_token")
            else:
                raise KeyError("Offline token not defined.")
            self.token_request_url = settings.get("url").get("token_request")
            self.allocations_url = settings.get("url").get("allocations")
            self._access_token = None
            self._allocations = None
            self.token_request_data = {
                "grant_type": "refresh_token",
                "client_id": "rhsm-api",
                "refresh_token": self.offline_token,
            }
            self.manifest_data = {"proxies": proxies}
            self.username_prefix = settings.get("username_prefix")
            if kwargs.get("requester") is not None:
                self.requester = kwargs["requester"]
                self.is_mock = True
            else:
                import requests

                self.requester = requests
                self.is_mock = False
        else:
            if isinstance(manifest_category, dict):
                self.manifest_data = DynaBox(manifest_category)
            else:
                self.manifest_data = settings.manifest_category.get(manifest_category)
            if kwargs.get("requester") is not None:
                self.requester = kwargs["requester"]
                self.is_mock = True
            else:
                import requests

                self.requester = requests
                self.is_mock = False
            self.username_prefix = (
                self.manifest_data.get("username_prefix") or settings.username_prefix
            )
            self.allocation_name = allocation_name or f"{self.username_prefix}-" + "".join(
                random.sample(string.ascii_letters, 8)
            )
            self.manifest_name = Path(f"{self.allocation_name}_manifest.zip")
            self.offline_token = self.manifest_data.get(
                "offline_token", settings.get("offline_token")
            )
            self.subscription_data = self.manifest_data.subscription_data
            self.token_request_data = {
                "grant_type": "refresh_token",
                "client_id": "rhsm-api",
                "refresh_token": self.offline_token,
            }
            self.simple_content_access = kwargs.get(
                "simple_content_access", self.manifest_data.simple_content_access
            )
            self.token_request_url = self.manifest_data.get("url").get("token_request")
            self.allocations_url = self.manifest_data.get("url").get("allocations")
            self._access_token = None
            self._allocations = None
            self._subscription_pools = None
            self._active_pools = []
            self.sat_version = process_sat_version(
                kwargs.get("sat_version", self.manifest_data.sat_version),
                self.valid_sat_versions,
            )

    @property
    def access_token(self):
        """Representation of an RHSM API access token.

        Used to authenticate requests to the RHSM API.
        """
        if not self._access_token:
            token_request_data = {"data": self.token_request_data}
            logger.debug("Generating access token")
            token_data = simple_retry(
                self.requester.post,
                cmd_args=[f"{self.token_request_url}"],
                cmd_kwargs=token_request_data,
            ).json()
            if "error" in token_data:
                raise RequestException(f"{token_data['error']}: {token_data['error_description']}")
            if self.is_mock:
                self._access_token = token_data.access_token
            else:
                self._access_token = token_data["access_token"]
        return self._access_token

    @cached_property
    def valid_sat_versions(self):
        """Retrieves the list of valid Satellite versions from the RHSM API."""
        headers = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies"),
        }
        sat_versions_response = simple_retry(
            self.requester.get,
            cmd_args=[f"{self.allocations_url}/versions"],
            cmd_kwargs=headers,
        ).json()
        if self.is_mock:
            sat_versions_response = sat_versions_response.version_response
        valid_sat_versions = [ver_dict["value"] for ver_dict in sat_versions_response["body"]]
        return valid_sat_versions

    @property
    def subscription_allocations(self):
        """Representation of subscription allocations in an account.

        Filtered by username_prefix.
        """
        return fetch_paginated_data(self, "allocations")

    @property
    def subscription_pools(self):
        """Representation of subscription pools in an account."""
        return fetch_paginated_data(self, "pools")

    def create_subscription_allocation(self):
        """Creates a new consumer in the provided RHSM account and returns its UUID."""
        allocation_data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies"),
            "params": {
                "name": f"{self.allocation_name}",
                "version": f"{self.sat_version}",
                "simpleContentAccess": f"{self.simple_content_access}",
            },
        }
        self.allocation = simple_retry(
            self.requester.post,
            cmd_args=[f"{self.allocations_url}"],
            cmd_kwargs=allocation_data,
        ).json()
        logger.debug(f"Received response {self.allocation} when attempting to create allocation.")
        self.allocation_uuid = self.allocation["body"]["uuid"]
        if self.simple_content_access == "disabled":
            simple_retry(
                self.requester.put,
                cmd_args=[f"{self.allocations_url}/{self.allocation_uuid}"],
                cmd_kwargs={
                    "headers": {"Authorization": f"Bearer {self.access_token}"},
                    "proxies": self.manifest_data.get("proxies"),
                    "json": {"simpleContentAccess": "disabled"},
                },
            )
        logger.info(
            f"Subscription allocation created with name {self.allocation_name} "
            f"and UUID {self.allocation_uuid}"
        )
        update_inventory(self.subscription_allocations)
        return self.allocation_uuid

    def delete_subscription_allocation(self, uuid=None):
        """Deletes the specified subscription allocation and returns the RHSM API's response."""
        self._access_token = None
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies"),
            "params": {"force": "true"},
        }
        if self.is_mock:
            self.allocation_uuid = self.allocation_uuid.uuid
        response = simple_retry(
            self.requester.delete,
            cmd_args=[f"{self.allocations_url}/{uuid if uuid else self.allocation_uuid}"],
            cmd_kwargs=data,
        )
        update_inventory(self.subscription_allocations)
        return response

    def add_entitlements_to_allocation(self, pool_id, entitlement_quantity):
        """Attempts to add the set of subscriptions defined in the settings to the allocation."""
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies"),
            "params": {"pool": f"{pool_id}", "quantity": f"{entitlement_quantity}"},
        }
        add_entitlements = simple_retry(
            self.requester.post,
            cmd_args=[f"{self.allocations_url}/{self.allocation_uuid}/entitlements"],
            cmd_kwargs=data,
        )
        return add_entitlements

    def verify_allocation_entitlements(self, entitlement_quantity, subscription_name):
        """Checks that the entitlements in the allocation match those defined in settings."""
        logger.info(f"Verifying the entitlement quantity of {subscription_name} on the allocation.")
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies"),
            "params": {"include": "entitlements"},
        }
        self.entitlement_data = simple_retry(
            self.requester.get,
            cmd_args=[f"{self.allocations_url}/{self.allocation_uuid}"],
            cmd_kwargs=data,
        ).json()
        current_entitlement = [
            d
            for d in self.entitlement_data["body"]["entitlementsAttached"]["value"]
            if d["subscriptionName"] == subscription_name
        ]
        if not current_entitlement:
            return
        logger.debug(f"Current entitlement is {current_entitlement}")
        self.attached_quantity = current_entitlement[0]["entitlementQuantity"]
        if self.attached_quantity == entitlement_quantity:
            logger.debug(f"Operation successful. Attached {self.attached_quantity} entitlements.")
            return True
        elif self.attached_quantity < entitlement_quantity:
            logger.debug(
                f"{self.attached_quantity} of {entitlement_quantity} attached. Trying again."
            )
            return
        else:
            logger.warning(
                f"Something went wrong. Attached quantity {self.attached_quantity} is greater than "
                f"requested quantity {entitlement_quantity}."
            )
            return True

    def process_subscription_pools(self, subscription_pools, subscription_data):
        """Loops through the list of subscription pools in the account.

        Identifies pools that match the subscription names and quantities defined in settings, then
        attempts to add the specified quantity of each subscription to the allocation.
        """
        SUCCESS_CODE = 200
        logger.debug(f"Finding a matching pool for {subscription_data['name']}.")
        matching = [
            d
            for d in subscription_pools["body"]
            if d["subscriptionName"] == subscription_data["name"]
        ]
        logger.debug(f"The following pools are matches for this subscription: {matching}")
        for match in matching:
            if (
                match["entitlementsAvailable"] > subscription_data["quantity"]
                or match["entitlementsAvailable"] == -1
            ):
                logger.debug(
                    f"Pool {match['id']} is a match for this subscription and has "
                    f"{match['entitlementsAvailable']} entitlements available."
                )
                add_entitlements = self.add_entitlements_to_allocation(
                    pool_id=match["id"],
                    entitlement_quantity=subscription_data["quantity"],
                )
                # if the above is using simple_retry, it will raise an exception
                # and never trigger the following block
                if add_entitlements.status_code in [404, 429, 500, 504]:
                    verify_entitlements = self.verify_allocation_entitlements(
                        entitlement_quantity=subscription_data["quantity"],
                        subscription_name=subscription_data["name"],
                    )
                    if not verify_entitlements:
                        # If no entitlements of a given subscription are
                        # attached, refresh the pools and try again
                        if not self.attached_quantity:
                            self._subscription_pools = None
                            # self.subscription_pools
                            self.process_subscription_pools(
                                subscription_pools=self.subscription_pools,
                                subscription_data=subscription_data,
                            )
                        # If non-zero but insufficient entitlements are
                        # attached, find the difference between the
                        # attached quantity and the desired quantity, refresh
                        # the pools, and try again
                        else:
                            logger.debug(
                                f"Received response status {add_entitlements.status_code}."
                                "Trying to find another pool."
                            )
                            self._subscription_pools = None
                            subscription_data["quantity"] -= self.attached_quantity
                            self.process_subscription_pools(
                                subscription_pools=self.subscription_pools,
                                subscription_data=subscription_data,
                            )
                    else:
                        logger.debug(
                            f"Successfully added {subscription_data['quantity']} entitlements of "
                            f"{subscription_data['name']} to the allocation."
                        )
                        self._active_pools.append(match)
                        update_inventory(self.subscription_allocations)
                        break
                elif add_entitlements.status_code == SUCCESS_CODE:
                    logger.debug(
                        f"Successfully added {subscription_data['quantity']} entitlements of "
                        f"{subscription_data['name']} to the allocation."
                    )
                    self._active_pools.append(match)
                    update_inventory(self.subscription_allocations)
                    break
                else:
                    raise RuntimeError(
                        "Something went wrong while adding entitlements. Received response status "
                        f"{add_entitlements.status_code}."
                    )

    def trigger_manifest_export(self):
        """Triggers job to export manifest from subscription allocation.

        Starts the export job, monitors the status of the job, and downloads the manifest on
        successful completion of the job.
        """
        MAX_REQUESTS = 500
        SUCCESS_CODE = 200
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies"),
        }
        local_file = Path(f"manifests/{self.manifest_name}")
        local_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Triggering manifest export job for subscription allocation {self.allocation_name}"
        )
        trigger_export_job = simple_retry(
            self.requester.get,
            cmd_args=[f"{self.allocations_url}/{self.allocation_uuid}/export"],
            cmd_kwargs=data,
        ).json()
        export_job_id = trigger_export_job["body"]["exportJobID"]
        export_job = simple_retry(
            self.requester.get,
            cmd_args=[f"{self.allocations_url}/{self.allocation_uuid}/exportJob/{export_job_id}"],
            cmd_kwargs=data,
        )
        request_count = 1
        limit_exceeded = False
        while export_job.status_code != SUCCESS_CODE:
            export_job = simple_retry(
                self.requester.get,
                cmd_args=[
                    f"{self.allocations_url}/{self.allocation_uuid}/exportJob/{export_job_id}"
                ],
                cmd_kwargs=data,
            )
            logger.debug(f"Attempting to export manifest. Attempt number: {request_count}")
            if request_count > MAX_REQUESTS:
                limit_exceeded = True
                logger.info(
                    "Manifest export job status check limit exceeded. This may indicate an "
                    "upstream issue with Red Hat Subscription Management."
                )
                raise Timeout("Export timeout exceeded")
            request_count += 1
        if limit_exceeded:
            self.content = None
            return self
        export_job = export_job.json()
        if self.is_mock:
            export_href = export_job.body["href"]
        else:
            export_href = export_job["body"]["href"]
        manifest = simple_retry(
            self.requester.get,
            cmd_args=[f"{export_href}"],
            cmd_kwargs=data,
        )
        logger.info(
            f"Writing manifest for subscription allocation {self.allocation_name} to location "
            f"{local_file}"
        )
        local_file.write_bytes(manifest.content)
        manifest.path = local_file
        manifest.name = self.manifest_name
        if self.is_mock:
            manifest.uuid = self.allocation_uuid.uuid
        else:
            manifest.uuid = self.allocation_uuid
        update_inventory(self.subscription_allocations)
        return manifest

    def get_manifest(self):
        """Provides a subscription manifest based on settings.

        Calls the methods required to create a new subscription allocation, add the appropriate
        subscriptions to the allocation, export a manifest, and download the manifest.
        """
        self.create_subscription_allocation()
        for sub in self.subscription_data:
            self.process_subscription_pools(
                subscription_pools=self.subscription_pools,
                subscription_data=sub,
            )
        return self.trigger_manifest_export()

    def __enter__(self):
        """Generates and returns a manifest."""
        try:
            return self.get_manifest()
        except:
            self.delete_subscription_allocation()
            raise

    def __exit__(self, *tb_args):
        """Deletes subscription allocation on teardown unless using CLI."""
        self.delete_subscription_allocation()
        update_inventory(self.subscription_allocations)
