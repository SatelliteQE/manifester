import random
import time

from collections import UserDict
from logzero import logger


def simple_retry(cmd, cmd_args=None, cmd_kwargs=None, max_timeout=2, _cur_timeout=1):
    """Re(Try) a function given its args and kwargs up until a max timeout"""

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
    """Ensure that the sat_version parameter is properly formatted for the RHSM API when creating
       a subscription allocation with the 'POST allocations' endpoint"""
    if sat_version not in valid_sat_versions:
        # The valid values for the sat_version parameter when creating a subscription allocation
        # are all 8 characters or less (e.g. 'sat-6.11'). Some data sources may include a Z-stream
        # version (e.g. 'sat-6.11.0') when retrieving this value from settings. The conditional
        # below assumes that, if the length of sat_version is greated than 8 characters, it includes
        # a Z-stream version that should be removed.
        if len(sat_version) > 8:
            sat_version = sat_version.split('.')
            sat_version = sat_version[0:2]
            sat_version = ".".join(sat_version)
        # If sat_version is still not valid, default to the latest valid version.
        if sat_version not in valid_sat_versions:
            valid_sat_versions.sort(key = lambda i: int(i.split('-')[-1].split('.')[-1]), reverse = True)
            return valid_sat_versions[0]
    return sat_version

def fake_http_response_code(good_codes=None, bad_codes=None, fail_rate=20):
    """Return an HTTP response code randomly selected from sets of good and bad codes"""

    if random.random() > (fail_rate / 100):
        return random.choice(good_codes)
    else:
        return random.choice(bad_codes)


class MockStub(UserDict):
    """Test helper class. Allows for both arbitrary mocking and stubbing"""

    def __init__(self, in_dict=None):
        """Initialize the class and all nested dictionaries"""
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
        return self

    def __getitem__(self, key):
        if isinstance(key, str):
            item = getattr(self, key, self)
        try:
            item = super().__getitem__(key)
        except KeyError:
            item = self
        return item

    def __call__(self, *args, **kwargs):
        return self
