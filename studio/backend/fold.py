"""
Where LinkedIn cuts a post off behind "see more", in one place.
================================================================

The studio's central promise about a draft is whether its opening survives
the mobile fold. That verdict was computed in four modules with two different
limits: 140 characters in the formatter and the ingress parser, 180 in the
content copilot and the scar-tissue check (which also declared a 140 constant
and then passed 180 past it). The same draft could be called safe by one
endpoint and truncated by the other.

Every check imports these instead of carrying its own number.
"""

# Characters of the opening that show before "see more" on mobile.
MOBILE_FOLD_CHARS = 140

# Visual lines that show before "see more" on mobile.
MOBILE_FOLD_LINES = 3
