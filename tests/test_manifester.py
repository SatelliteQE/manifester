from unittest.mock import Mock

from requests import request
from manifester import Manifester
from manifester.settings import settings
from manifester.helpers import MockStub, fake_http_response_code
import pytest
import random

def test_empty_init(manifest_category="golden_ticket"):
    manifester_inst = Manifester(manifest_category=manifest_category)
    assert isinstance(manifester_inst, Manifester)

class RhsmApiStub(MockStub):
    def __init__(self, in_dict=None, **kwargs):
        self._good_codes = kwargs.get("good_codes", [200])
        self._bad_codes = kwargs.get("bad_codes", [429, 500, 504])
        self._fail_rate = kwargs.get("fail_rate", 10)
        super().__init__(in_dict)

    @property
    def status_code(self):
        return fake_http_response_code(self._good_codes, self._bad_codes, self._fail_rate)

    def post(*args, **kwargs):
        if args[0].endswith("openid-connect/token"):
            return MockStub(in_dict={"access_token": "this is a simulated access token"}, status_code=200)
        if args[0].endswith("allocations"):
            return MockStub(in_dict={"uuid": "1234567890"})
        if args[0].endswith("entitlements"):
            return MockStub(status_code=200)

    def get(*args, **kwargs):
        if args[0].endswith("pools"):
            # question: how to fake > 50 pools to test use of offset parameter?
            return MockStub(in_dict={"pool": "this is a simulated list of dictionaries of subscription pool data"})
        if "allocations" in args[0] and not ("export" in args[0] or "pools" in args[0]):
            return MockStub(in_dict={"allocation_data": "this allocation data also includes entitlement data"})
        if args[0].endswith("export"):
            return MockStub(in_dict={"export_job": "Manifest export job triggered successfully"})
        if "exportJob" in args[0]:
            responses = [202, 200]
            return MockStub(status_code=random.choice(responses))
        if "export" in args[0] and not args[0].endswith("export"):
            return MockStub(in_dict={"content": "this is a simulated manifest"})


def test_create_allocation():
    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None, status_code=200))
    allocation_uuid = manifester.create_subscription_allocation()
    breakpoint()
    assert allocation_uuid == "1234567890"
