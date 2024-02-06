"""Defines helper functions used by Manifester."""
from collections import UserDict
from pathlib import Path
import random
import time

from logzero import logger
from requests import HTTPError
import yaml

from manifester.settings import settings

MAX_RESULTS_PER_PAGE = 50
RESULTS_LIMIT = 10000


def simple_retry(cmd, cmd_args=None, cmd_kwargs=None, max_timeout=240, _cur_timeout=1):
    """Re(Try) a function given its args and kwargs up until a max timeout."""
    cmd_args = cmd_args if cmd_args else []
    cmd_kwargs = cmd_kwargs if cmd_kwargs else {}
    # If additional debug information is needed, the following log entry can be modified to
    # include the data being passed by adding {cmd_kwargs=} to the f-string. Please do so
    # with caution as some data (notably the offline token) should be treated as a secret.
    logger.debug(f"Sending request to endpoint {cmd_args}")
    response = cmd(*cmd_args, **cmd_kwargs)
    logger.debug(f"Response status code is {response.status_code}")
    if response.status_code in [429, 500, 504]:
        new_wait = _cur_timeout * 2
        if new_wait > max_timeout:
            raise Exception("Retry timeout exceeded")
        logger.debug(f"Trying again in {_cur_timeout} seconds")
        time.sleep(_cur_timeout)
        response = simple_retry(cmd, cmd_args, cmd_kwargs, max_timeout, new_wait)
    return response


def process_sat_version(sat_version, valid_sat_versions):
    """Ensure that the sat_version parameter is properly formatted for the RHSM API."""
    expected_length = 8
    if sat_version not in valid_sat_versions:
        # The valid values for the sat_version parameter when creating a subscription allocation
        # are all 8 characters or less (e.g. 'sat-6.11'). Some data sources may include a Z-stream
        # version (e.g. 'sat-6.11.0') when retrieving this value from settings. The conditional
        # below assumes that, if the length of sat_version is greated than 8 characters, it includes
        # a Z-stream version that should be removed.
        if len(sat_version) > expected_length:
            sat_version = sat_version.split(".")
            sat_version = sat_version[0:2]
            sat_version = ".".join(sat_version)
        # If sat_version is still not valid, default to the latest valid version.
        if sat_version not in valid_sat_versions:
            valid_sat_versions.sort(
                key=lambda i: int(i.split("-")[-1].split(".")[-1]), reverse=True
            )
            return valid_sat_versions[0]
    return sat_version


def fetch_paginated_data(manifester, endpoint):
    """Fetch data from the API and account for pagination in the API response.

    Currently used only for subscription allocations and subscription pools.
    """
    if endpoint == "allocations":
        _endpoint_url = manifester.allocations_url
        _endpoint_data = manifester._allocations
    elif endpoint == "pools":
        _endpoint_url = f"{manifester.allocations_url}/{manifester.allocation_uuid}/pools"
        _endpoint_data = manifester._subscription_pools
    else:
        raise ValueError(
            f"Received value {endpoint} for endpoint argument. Valid values "
            "for endpoint are 'allocations' or 'pools'."
        )
    if not _endpoint_data:
        _offset = 0
        data = {
            "headers": {"Authorization": f"Bearer {manifester.access_token}"},
            "proxies": manifester.manifest_data.get("proxies"),
            "params": {
                "offset": _offset,
                "limit": RESULTS_LIMIT,
            },
        }
        _endpoint_data = simple_retry(
            manifester.requester.get,
            cmd_args=[f"{_endpoint_url}"],
            cmd_kwargs=data,
        ).json()
        if _endpoint_data.status_code in [400, 401, 403, 404]:
            raise HTTPError(
                f"Received HTTP {_endpoint_data.status_code} response code. Please "
                "ensure that the request is a properly-formatted and authorized "
                "request to a valid endpoint."
            )
        if manifester.is_mock and endpoint == "pools":
            _endpoint_data = _endpoint_data.pool_response
        elif manifester.is_mock and endpoint == "allocations":
            _endpoint_data = _endpoint_data.allocations_response
        _results = len(_endpoint_data["body"])
        # The endpoints used in the above API call can return a maximum of 50 results. For
        # organizations with more than 50 subscription allocations or pools, the loop below works
        # around this limit by repeating calls with a progressively larger value for the `offset`
        # parameter.
        while _results == MAX_RESULTS_PER_PAGE:
            _offset += 50
            logger.debug(f"Fetching additional data with an offset of {_offset}.")
            data = {
                "headers": {"Authorization": f"Bearer {manifester.access_token}"},
                "proxies": manifester.manifest_data.get("proxies"),
                "params": {"offset": _offset, "limit": RESULTS_LIMIT},
            }
            offset_data = simple_retry(
                manifester.requester.get,
                cmd_args=[f"{_endpoint_url}"],
                cmd_kwargs=data,
            ).json()
            if offset_data.status_code in [400, 401, 403, 404]:
                raise HTTPError(
                    f"Received HTTP {_endpoint_data.status_code} response code. Please "
                    "ensure that the request is a properly-formatted and authorized "
                    "request to a valid endpoint."
                )
            if manifester.is_mock and endpoint == "pools":
                offset_data = offset_data.pool_response
            elif manifester.is_mock and endpoint == "allocations":
                offset_data = offset_data.allocations_response
            _endpoint_data["body"] += offset_data["body"]
            _results = len(offset_data["body"])
            total_results = len(_endpoint_data["body"])
            logger.debug(f"Total {endpoint} available on this account: {total_results}")
    if endpoint == "allocations":
        if hasattr(_endpoint_data, "force_export_failure"):
            return [
                a
                for a in _endpoint_data.allocation_data["body"]
                if a["name"].startswith(manifester.username_prefix)
            ]
        else:
            return [
                a
                for a in _endpoint_data["body"]
                if a["name"].startswith(manifester.username_prefix)
            ]
    elif endpoint == "pools":
        return _endpoint_data


def load_inventory_file(file):
    """Load local inventory file.

    :return: list of dictionaries
    """
    if file.suffix in (".yaml", ".yml"):
        loader = yaml
        loader_args = {"Loader": yaml.FullLoader}
        with file.open() as f:
            return loader.load(f, **loader_args) or []
    else:
        logger.warn(
            f"Found invalid inventory file {file}. Inventory file must exist and "
            "have a .yaml or .yml suffix."
        )


def update_inventory(inventory_data):
    """Replace the existing inventory file with current subscription allocations."""
    inventory_path = Path(settings.inventory_path)
    if load_inventory_file(inventory_path):
        inventory_path.unlink()
    inventory_path.touch()
    if inventory_data != []:
        with inventory_path.open("w") as inventory_file:
            yaml.dump(inventory_data, inventory_file, allow_unicode=True)


def fake_http_response_code(good_codes=None, bad_codes=None, fail_rate=0):
    """Return an HTTP response code randomly selected from sets of good and bad codes."""
    if random.random() > (fail_rate / 100):
        return random.choice(good_codes)
    else:
        return random.choice(bad_codes)


class MockStub(UserDict):
    """Test helper class. Allows for both arbitrary mocking and stubbing."""

    def __init__(self, in_dict=None):
        """Initialize the class and all nested dictionaries."""
        if in_dict is None:
            in_dict = {}
        for key, value in in_dict.items():
            if isinstance(value, dict):
                setattr(self, key, MockStub(value))
            elif type(value) in (list, tuple):
                setattr(
                    self,
                    key,
                    [MockStub(x) if isinstance(x, dict) else x for x in value],
                )
            else:
                setattr(self, key, value)
        super().__init__(in_dict)

    def __getattr__(self, name):
        """Fallback to returning self if attribute doesn't exist."""
        return self

    def __getitem__(self, key):
        """Get an item from the dictionary-like object.

        If the key is a string, this method will attempt to get an attribute with that name.
        If the key is not found, this method will return the object itself.
        """
        if isinstance(key, str):
            item = getattr(self, key, self)
        try:
            item = super().__getitem__(key)
        except KeyError:
            item = self
        return item

    def __call__(self, *args, **kwargs):
        """Allow MockStub to be used like a function."""
        return self
