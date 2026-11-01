import pytest
import responses
from tenacity import wait_none

from app.meta.errors import meta_error_from_body
from app.meta.fake import STEP_FOR_EDGE, FakeAdsGateway
from app.meta.sdk_gateway import GRAPH_URL, MetaSdkGateway
from tests.meta_payloads import M0_ACCOUNT


class FakeWorld:
    """The fake keeps real state, so most preparations are no-ops."""

    PAGE_WITH_INSTAGRAM = "page_fake_1"

    def __init__(self, fake: FakeAdsGateway):
        self.fake = fake

    def replay(self, method: str, path: str, body: dict, status: int = 200) -> None:
        pass

    def created(self, edge: str, object_id: str) -> None:
        pass

    def found(self, edge: str, object_id: str | None) -> None:
        pass

    def updated(self, object_id: str) -> None:
        pass

    def deleted(self, object_id: str) -> None:
        pass

    def create_fails(self, edge: str, body: dict, status: int = 400) -> None:
        self.fake.fail_at[STEP_FOR_EDGE[edge]] = meta_error_from_body(body, status)


class SdkWorld:
    """Registers the HTTP response Meta would send; the real SDK parses it."""

    PAGE_WITH_INSTAGRAM = "1415879818267624"

    def __init__(self, mock: responses.RequestsMock, version: str):
        self.mock, self.base = mock, f"{GRAPH_URL}/{version}"

    def replay(self, method: str, path: str, body: dict, status: int = 200) -> None:
        self.mock.add(method, f"{self.base}/{path}", json=body, status=status)

    def created(self, edge: str, object_id: str) -> None:
        self.replay("POST", f"{M0_ACCOUNT}/{edge}", {"id": object_id})

    def found(self, edge: str, object_id: str | None) -> None:
        self.replay("GET", f"{M0_ACCOUNT}/{edge}", {"data": [{"id": object_id}] if object_id else []})

    def updated(self, object_id: str) -> None:
        self.replay("POST", object_id, {"success": True})

    def deleted(self, object_id: str) -> None:
        self.replay("DELETE", object_id, {"success": True})

    def create_fails(self, edge: str, body: dict, status: int = 400) -> None:
        self.replay("POST", f"{M0_ACCOUNT}/{edge}", body, status)


@pytest.fixture(params=["fake", "sdk"])
def gateway_and_world(request, settings):
    if request.param == "fake":
        fake = FakeAdsGateway()
        yield fake, FakeWorld(fake)
        return
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        gateway = MetaSdkGateway(access_token="TEST-TOKEN", settings=settings, wait=wait_none())
        yield gateway, SdkWorld(mock, settings.meta_api_version)


@pytest.fixture
def gateway(gateway_and_world):
    return gateway_and_world[0]


@pytest.fixture
def world(gateway_and_world):
    return gateway_and_world[1]


@pytest.fixture
def account():
    return M0_ACCOUNT
