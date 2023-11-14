from unittest.mock import Mock

from requests import request
from manifester import Manifester
from manifester.settings import settings
from manifester.helpers import MockStub, fake_http_response_code
import pytest
import random

def test_empty_init(manifest_category="golden_ticket"):
    manifester_inst = Manifester(manifest_category=manifest_category, requester=RhsmApiStub(in_dict=None))
    breakpoint()
    assert isinstance(manifester_inst, Manifester)
    assert manifester_inst.access_token == 'this is a simulated access token'

class RhsmApiStub(MockStub):
    def __init__(self, in_dict=None, **kwargs):
        self._good_codes = kwargs.get("good_codes", [200])
        self._bad_codes = kwargs.get("bad_codes", [429, 500, 504])
        self._fail_rate = kwargs.get("fail_rate", 10)
        self.status_code = fake_http_response_code(self._good_codes, self._bad_codes, self._fail_rate)
        super().__init__(in_dict)

    # @property
    # def status_code(self):
    #     return fake_http_response_code(self._good_codes, self._bad_codes, self._fail_rate)

    def post(*args, **kwargs):
        if args[1].endswith("openid-connect/token"):
            return RhsmApiStub(in_dict={"access_token": "this is a simulated access token"})
        if args[1].endswith("allocations/"):
            return RhsmApiStub(in_dict={"uuid": "1234567890"})
        if args[1].endswith("entitlements"):
            return RhsmApiStub(status_code=200)

    def get(*args, **kwargs):
        if args[1].endswith("versions"):
            return RhsmApiStub(in_dict={"valid_sat_versions": ["sat-6.12", "sat-6.13", "sat-6.14"]})
        if args[1].endswith("pools"):
            # question: how to fake > 50 pools to test use of offset parameter?
            return MockStub(in_dict={"pool": "this is a simulated list of dictionaries of subscription pool data"})
        if "allocations" in args[1] and not ("export" in args[1] or "pools" in args[1]):
            return MockStub(in_dict={"allocation_data": "this allocation data also includes entitlement data"})
        if args[1].endswith("export"):
            return MockStub(in_dict={"export_job": "Manifest export job triggered successfully"})
        if "exportJob" in args[1]:
            responses = [202, 200]
            return MockStub(status_code=random.choice(responses))
        if "export" in args[1] and not args[1].endswith("export"):
            return MockStub(in_dict={"content": "this is a simulated manifest"})


def test_create_allocation():
    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None, status_code=200))
    allocation_uuid = manifester.create_subscription_allocation()
    assert allocation_uuid == "1234567890"
