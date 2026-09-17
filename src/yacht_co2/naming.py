"""One name for every artifact a campaign produces.

Products from several campaigns end up in one folder, on one Zenodo record or
one desktop, where ``track.nc`` says nothing about which campaign it came from.
Every output is therefore named ``yacht_co2-<campaign>-<date>-<kind>.<ext>``:
the hyphen separates the fields, and within a field every run of other
characters -- a space, a dot, the hyphens of an ISO date -- collapses to an
underscore, so ``Fastnet Race`` on ``2023-07-24`` reads as
``yacht_co2-fastnet_race-2023_07_24-track.nc`` and the fields stay legible.
"""

from __future__ import annotations

import re

PREFIX = "yacht_co2"


def field_slug(value: str) -> str:
    """Slugify one field of an artifact name: lower case, underscores within."""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def campaign_slug(campaign: str, campaign_date: str) -> str:
    """Return the ``<campaign>-<date>`` part of an artifact name."""
    fields = [field for field in (field_slug(campaign), field_slug(campaign_date)) if field]
    if not fields:
        raise ValueError("campaign and campaign date cannot both be empty")
    return "-".join(fields)


def output_stem(campaign: str, campaign_date: str, kind: str) -> str:
    """Name one artifact of a campaign, without an extension.

    ``kind`` says what the artifact is -- ``track``, ``report``, ``site``,
    ``video``, or ``product-<name>`` -- so its own hyphen separates two fields
    and a provider name carrying a dot or a space stays one of them.
    """
    kind_slug = "-".join(field_slug(field) for field in kind.split("-"))
    return f"{PREFIX}-{campaign_slug(campaign, campaign_date)}-{kind_slug}"


def output_name(campaign: str, campaign_date: str, kind: str, extension: str) -> str:
    """Name one artifact of a campaign, extension included."""
    return f"{output_stem(campaign, campaign_date, kind)}.{extension.lstrip('.')}"
