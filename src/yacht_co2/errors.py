"""Package exception hierarchy."""


class YachtCO2Error(Exception):
    """Base error for the processing pipeline."""


class ManifestError(YachtCO2Error):
    """The campaign manifest is absent or invalid."""


class ParseError(YachtCO2Error):
    """A log cannot be parsed without losing its meaning."""


class ProviderError(YachtCO2Error):
    """A required environmental product could not be obtained."""


class ZenodoError(YachtCO2Error):
    """Zenodo configuration or upload processing failed."""


class RecordPublishedError(ZenodoError):
    """The Zenodo record is already published, so its files are immutable."""
