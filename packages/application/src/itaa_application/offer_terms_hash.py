"""Canonical OfferTerms digest for buyer, A3, A4, and recorded acceptance."""

from __future__ import annotations

from itaa_domain.offer import OfferTerms
from itaa_domain.value_objects import PayloadHash
from itaa_policy.canonical import SEPARATOR_OFFER_TERMS, hash_canonical


def offer_terms_hash(terms: OfferTerms) -> PayloadHash:
    """Hash the complete authoritative OfferTerms primitive. Ranking is excluded."""
    return hash_canonical(SEPARATOR_OFFER_TERMS, terms.to_primitive())
