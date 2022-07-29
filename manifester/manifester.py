import random
import string
from pathlib import Path

import requests
from logzero import logger

from manifester.helpers import simple_retry
from manifester.logger import setup_logzero
from manifester.settings import settings


class Manifester:
    def __init__(self, manifest_category, allocation_name=None, **kwargs):
        self.allocation_name = allocation_name or "".join(
            random.sample(string.ascii_letters, 10)
        )
        self.manifest_data = settings.manifest_category.get(manifest_category)
        self.offline_token = kwargs.get(
            "offline_token", self.manifest_data.get("offline_token", settings.offline_token)
        )
        self.subscription_data = self.manifest_data.subscription_data
        self.sat_version = kwargs.get("sat_version", self.manifest_data.sat_version)
        self.token_request_data = {
            "grant_type": "refresh_token",
            "client_id": "rhsm-api",
            "refresh_token": self.offline_token,
        }
        self.simple_content_access = kwargs.get(
            "simple_content_access", self.manifest_data.simple_content_access
        )
        self._access_token = None
        self._subscription_pools = None

    @property
    def access_token(self):
        if not self._access_token:
            token_request_data = {"data": self.token_request_data}
            logger.debug("Generating access token")
            token_data = simple_retry(
                requests.post,
                cmd_args=[f"{self.manifest_data.url.token_request}"],
                cmd_kwargs=token_request_data,
            ).json()
            self._access_token = token_data["access_token"]
        return self._access_token

    def create_subscription_allocation(self):
        allocation_data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies", settings.proxies),
            "params": {
                "name": f"{self.allocation_name}",
                "version": f"{self.sat_version}",
                "simpleContentAccess": f"{self.simple_content_access}",
            },
        }
        self.allocation = simple_retry(
            requests.post,
            cmd_args=[f"{self.manifest_data.url.allocations}"],
            cmd_kwargs=allocation_data,
        ).json()
        self.allocation_uuid = self.allocation["body"]["uuid"]
        logger.info(
            f"Subscription allocation created with name {self.allocation_name} "
            f"and UUID {self.allocation_uuid}"
        )
        return self.allocation_uuid

    @property
    def subscription_pools(self):
        if not self._subscription_pools:
            _offset = 0
            data = {
                "headers": {"Authorization": f"Bearer {self.access_token}"},
                "proxies": self.manifest_data.get("proxies", settings.proxies),
                "params": {"offset": _offset},
            }
            self._subscription_pools = simple_retry(
                requests.get,
                cmd_args=[
                    f"{self.manifest_data.url.allocations}/{self.allocation_uuid}/pools"
                ],
                cmd_kwargs=data,
            ).json()
            _results = len(self._subscription_pools["body"])
            # The endpoint used in the above API call can return a maximum of 50 subscription pools.
            # For organizations with more than 50 subscription pools, the loop below works around
            # this limit by repeating calls with a progressively larger value for the `offset`
            # parameter.
            while _results == 50:
                _offset += 50
                logger.debug(
                    f"Fetching additional subscription pools with an offset of {_offset}."
                )
                data = {
                    "headers": {"Authorization": f"Bearer {self.access_token}"},
                    "proxies": self.manifest_data.get("proxies", settings.proxies),
                    "params": {"offset": _offset},
                }
                offset_pools = simple_retry(
                    requests.get,
                    cmd_args=[
                        f"{self.manifest_data.url.allocations}/{self.allocation_uuid}/pools"
                    ],
                    cmd_kwargs=data,
                ).json()
                self._subscription_pools["body"] += offset_pools["body"]
                _results = len(offset_pools["body"])
                total_pools = len(self._subscription_pools["body"])
                logger.debug(
                    f"Total subscription pools available for this allocation: {total_pools}"
                )
        return self._subscription_pools

    def add_entitlements_to_allocation(self, pool_id, entitlement_quantity):
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies", settings.proxies),
            "params": {"pool": f"{pool_id}", "quantity": f"{entitlement_quantity}"},
        }
        add_entitlements = simple_retry(
            requests.post,
            cmd_args=[
                f"{self.manifest_data.url.allocations}/{self.allocation_uuid}/entitlements"
            ],
            cmd_kwargs=data,
        )
        return add_entitlements

    def verify_allocation_entitlements(self, entitlement_quantity, subscription_name):
        logger.info(
            f"Verifying the entitlement quantity of {subscription_name} on the allocation."
        )
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies", settings.proxies),
            "params": {"include": "entitlements"},
        }
        self.entitlement_data = simple_retry(
            requests.get,
            cmd_args=[f"{self.manifest_data.url.allocation}/{self.allocation_uuid}"],
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
            logger.debug(
                f"Operation successful. Attached {self.attached_quantity} entitlements."
            )
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
        logger.debug(f"Finding a matching pool for {subscription_data['name']}.")
        matching = [
            d
            for d in subscription_pools["body"]
            if d["subscriptionName"] == subscription_data["name"]
        ]
        logger.debug(
            f"The following pools are matches for this subscription: {matching}"
        )
        for match in matching:
            if match["entitlementsAvailable"] > subscription_data["quantity"]:
                logger.debug(
                    f"Pool {match['id']} is a match for this subscription and has "
                    f"{match['entitlementsAvailable']} entitlements available."
                )
                add_entitlements = self.add_entitlements_to_allocation(
                    pool_id=match["id"],
                    entitlement_quantity=subscription_data["quantity"],
                )
                # if the above is using simple_rety, it will raise an exception
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
                        break
                elif add_entitlements.status_code == 200:
                    logger.debug(
                        f"Successfully added {subscription_data['quantity']} entitlements of "
                        f"{subscription_data['name']} to the allocation."
                    )
                    break
                else:
                    raise Exception(
                        "Something went wrong while adding entitlements. Received response status "
                        f"{add_entitlements.status_code}."
                    )

    def trigger_manifest_export(self):
        data = {
            "headers": {"Authorization": f"Bearer {self.access_token}"},
            "proxies": self.manifest_data.get("proxies", settings.proxies),
        }
        # Should this use the XDG Base Directory Specification?
        local_file = Path(f"manifests/{self.allocation_name}_manifest.zip")
        local_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Triggering manifest export job for subscription allocation {self.allocation_name}"
        )
        trigger_export_job = simple_retry(
            requests.get,
            cmd_args=[
                f"{self.manifest_data.url.allocations}/{self.allocation_uuid}/export"
            ],
            cmd_kwargs=data,
        ).json()
        export_job_id = trigger_export_job["body"]["exportJobID"]
        export_job = simple_retry(
            requests.get,
            cmd_args=[
                f"{self.manifest_data.url.allocations}/{self.allocation_uuid}/exportJob/{export_job_id}"
            ],
            cmd_kwargs=data,
        )
        request_count = 1
        limit_exceeded = False
        while export_job.status_code != 200:
            export_job = simple_retry(
                requests.get,
                cmd_args=[
                    f"{self.manifest_data.url.allocations}/{self.allocation_uuid}/exportJob/{export_job_id}"
                ],
                cmd_kwargs=data,
            )
            logger.debug(
                f"Attempting to export manifest. Attempt number: {request_count}"
            )
            if request_count > 50:
                limit_exceeded = True
                logger.info(
                    "Manifest export job status check limit exceeded. This may indicate an "
                    "upstream issue with Red Hat Subscription Management."
                )
                break
            request_count += 1
        if limit_exceeded:
            return
        export_job = export_job.json()
        export_href = export_job["body"]["href"]
        manifest = simple_retry(
            requests.get,
            cmd_args=[f"{export_href}"],
            cmd_kwargs=data,
        )
        logger.info(
            f"Writing manifest for subscription allocation {self.allocation_name} to location "
            f"{local_file}"
        )
        local_file.write_bytes(manifest.content)
        return manifest

    def get_manifest(self):
        self.create_subscription_allocation()
        for sub in self.subscription_data:
            self.process_subscription_pools(
                subscription_pools=self.subscription_pools,
                subscription_data=sub,
            )
        return self.trigger_manifest_export()
