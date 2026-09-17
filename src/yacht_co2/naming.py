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
from dataclasses import dataclass

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


#: The kinds of artifact a campaign run produces, other than the environmental
#: products, which are named ``product-<provider>``.
ARTIFACT_KINDS = ("track", "report", "site", "video")

# A date field is the one field of an artifact name whose shape is known: it is
# an ISO date, a month or a year with every hyphen collapsed to an underscore.
_DATE_FIELD_RE = re.compile(r"\d{4}(?:_\d{2}(?:_\d{2})?)?")


@dataclass(frozen=True)
class ArtifactName:
    """The fields an artifact name was built from.

    ``campaign`` and ``campaign_date`` are the slugs as they appear in the
    name, not the values they were made from: slugging is lossy, so
    ``Fastnet Race`` cannot be recovered from ``fastnet_race`` -- only
    something that slugs to it again.
    """

    campaign: str
    campaign_date: str
    kind: str
    extension: str

    @property
    def iso_date(self) -> str:
        """The campaign date as it was written before it was slugged.

        The date is the one field whose original form is recoverable: every
        separator in an ISO date is a hyphen, so undoing the collapse is
        unambiguous.
        """
        return self.campaign_date.replace("_", "-")


def parse_output_name(name: str) -> ArtifactName | None:
    """Read an artifact name back into the fields :func:`output_name` built it from.

    Returns ``None`` for anything this package did not name, which is how a
    record's own raw logs and a reader's stray notes are told apart from its
    products.
    """
    stem, separator, extension = name.rpartition(".")
    if not separator or not stem or not extension:
        return None
    prefix, separator, rest = stem.partition("-")
    if prefix != PREFIX or not separator:
        return None
    fields = rest.split("-")
    if len(fields) < 2 or not fields[0]:
        return None
    # The date is left out of a name whose campaign has none, so the second
    # field is the date only when it reads as one and something follows it.
    if len(fields) > 2 and _DATE_FIELD_RE.fullmatch(fields[1]):
        campaign_date, kind_fields = fields[1], fields[2:]
    else:
        campaign_date, kind_fields = "", fields[1:]
    if not all(kind_fields):
        return None
    return ArtifactName(fields[0], campaign_date, "-".join(kind_fields), extension)
