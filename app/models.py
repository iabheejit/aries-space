from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Pass(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    norad_id: int = Field(index=True)
    aos: datetime = Field(index=True)  # acquisition of signal (pass start)
    los: datetime  # loss of signal (pass end)
    max_elevation_deg: float
    direction: str  # e.g. "N -> S"
    computed_at: datetime
    tle_stale: bool = False


class Observation(SQLModel, table=True):
    """A telemetry observation ingested from SatNOGS.

    Raw payload is kept verbatim in raw_json (audit trail); the remaining
    columns are the normalized view over it.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    satnogs_observation_id: int = Field(index=True, unique=True)
    satellite_id: int = Field(index=True)  # NORAD catalog ID
    station_id: Optional[int] = None
    timestamp: datetime = Field(index=True)
    frequency: Optional[int] = None
    signal_quality: Optional[str] = None
    waterfall_url: Optional[str] = None
    audio_url: Optional[str] = None
    decoded_data: Optional[str] = None
    raw_json: str
    ingested_at: datetime
