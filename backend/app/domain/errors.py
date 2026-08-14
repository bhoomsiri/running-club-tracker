"""Domain errors. Stdlib only — the API layer maps these to HTTP status codes."""


class DomainError(Exception):
    """Base for every rule violation the domain can report."""


class InvalidRunError(DomainError):
    """A run's values fail the sanity rules."""


class InvalidMemberError(DomainError):
    """A member's details fail validation."""


class MemberNotFound(DomainError):
    """No member exists for this id."""


class InvalidHealthRecordError(DomainError):
    """A health measurement is outside the plausible range."""


class InvalidCampaignError(DomainError):
    """A campaign is malformed, or its config is missing a value its policy needs."""


class UnknownCampaignType(DomainError):
    """No policy is registered for this campaign type."""


class RewardUnavailable(DomainError):
    """The reward is not redeemable (inactive, or not part of this campaign)."""


class OutOfStock(DomainError):
    """The reward has no stock left."""


class InsufficientPoints(DomainError):
    """The member's balance is below the reward's cost."""


class InvalidLedgerEntry(DomainError):
    """A ledger row's reason and its reference don't agree."""


class ConsentRequired(DomainError):
    """Health data was processed without an active consent for the current wording."""


class InvalidConsentError(DomainError):
    """A consent record is malformed, or was withdrawn twice."""


class InvalidAuditEntry(DomainError):
    """An audit entry carries something that must never be logged."""


class NotAuthorized(DomainError):
    """The actor's role does not permit this action."""


class InvalidToken(DomainError):
    """The bearer token failed verification: bad signature, wrong issuer, or expired."""


class MemberAlreadyExists(DomainError):
    """This clerk_user_id already has a member row (two first requests raced)."""


class InvalidImage(DomainError):
    """An uploaded file is not an acceptable evidence image."""


class DuplicateEvidence(DomainError):
    """This member already submitted a run with this exact image."""


class ExtractionFailed(DomainError):
    """The extractor could not return a usable draft."""


class RunNotFound(DomainError):
    """No run exists for this id."""


class CampaignNotFound(DomainError):
    """No campaign exists for this id."""


class InvalidRewardError(DomainError):
    """A reward's details fail validation."""


class RedemptionNotFound(DomainError):
    """No redemption exists for this id."""


class RedemptionNotPending(DomainError):
    """This redemption has already been fulfilled or cancelled."""


class UnresolvedRuns(DomainError):
    """The member has runs still awaiting review, so their points are not settled."""


class EvidenceNotFound(DomainError):
    """No stored image for this key."""
