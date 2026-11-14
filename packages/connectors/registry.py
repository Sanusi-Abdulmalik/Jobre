from __future__ import annotations

from functools import lru_cache

from packages.common.http_client import JobreHttpClient
from packages.connectors.ats.ashby import AshbyConnector
from packages.connectors.ats.bamboohr import BambooHRConnector
from packages.connectors.ats.breezy_hr import BreezyHRConnector
from packages.connectors.ats.gem import GemConnector
from packages.connectors.ats.greenhouse import GreenhouseConnector
from packages.connectors.ats.jazzhr import JazzHRConnector
from packages.connectors.ats.lever import LeverConnector
from packages.connectors.ats.manatal import ManatalConnector
from packages.connectors.ats.personio import PersonioConnector
from packages.connectors.ats.pinpoint import PinpointConnector
from packages.connectors.ats.polymer import PolymerConnector
from packages.connectors.ats.recruitee import RecruiteeConnector
from packages.connectors.ats.smartrecruiters import SmartRecruitersConnector
from packages.connectors.ats.teamtailor import TeamtailorConnector
from packages.connectors.ats.trakstar import TrakstarConnector
from packages.connectors.ats.workable import WorkableConnector
from packages.connectors.ats.workday import WorkdayConnector
from packages.connectors.base import BaseConnector
from packages.connectors.catalog import PLATFORM_CATALOG, PlatformSpec
from packages.connectors.jobboards.jobboard_io import JobBoardIoConnector
from packages.connectors.jobboards.jobboardly import JobboardlyConnector
from packages.connectors.jobboards.niceboard import NiceboardConnector
from packages.connectors.jobboards.smartjobboard import SmartJobBoardConnector
from packages.connectors.jobboards.wp_job_manager import WPJobManagerConnector


CONNECTOR_CLASSES: dict[str, type[BaseConnector]] = {
    "ashby": AshbyConnector,
    "bamboohr": BambooHRConnector,
    "breezy_hr": BreezyHRConnector,
    "gem": GemConnector,
    "greenhouse": GreenhouseConnector,
    "jazzhr": JazzHRConnector,
    "lever": LeverConnector,
    "manatal": ManatalConnector,
    "personio": PersonioConnector,
    "pinpoint": PinpointConnector,
    "polymer": PolymerConnector,
    "recruitee": RecruiteeConnector,
    "smartrecruiters": SmartRecruitersConnector,
    "teamtailor": TeamtailorConnector,
    "trakstar": TrakstarConnector,
    "workable": WorkableConnector,
    "workday": WorkdayConnector,
    "niceboard": NiceboardConnector,
    "jobboard_io": JobBoardIoConnector,
    "smartjobboard": SmartJobBoardConnector,
    "jobboardly": JobboardlyConnector,
    "wp_job_manager": WPJobManagerConnector,
}


class ConnectorRegistry:
    """Centralized registry over all 78 required ATS and Job-Board platforms."""

    def __init__(self, http_client: JobreHttpClient | None = None) -> None:
        self._http_client = http_client
        self._specs_by_key: dict[str, PlatformSpec] = {s.connector_key: s for s in PLATFORM_CATALOG}

    def all_platform_specs(self) -> tuple[PlatformSpec, ...]:
        return PLATFORM_CATALOG

    def get_platform_spec(self, connector_key: str) -> PlatformSpec | None:
        return self._specs_by_key.get(connector_key)

    def has_connector(self, connector_key: str) -> bool:
        return connector_key in CONNECTOR_CLASSES

    def implemented_keys(self) -> list[str]:
        return sorted(CONNECTOR_CLASSES.keys())

    def get_connector(self, connector_key: str) -> BaseConnector:
        cls = CONNECTOR_CLASSES.get(connector_key)
        if cls is None:
            spec = self._specs_by_key.get(connector_key)
            label = spec.name if spec else connector_key
            raise KeyError(f"Connector for platform '{label}' ({connector_key}) is not yet implemented.")
        return cls(http_client=self._http_client)


@lru_cache(maxsize=1)
def get_connector_registry() -> ConnectorRegistry:
    return ConnectorRegistry()
