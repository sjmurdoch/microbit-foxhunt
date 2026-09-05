"""Settings shared by both roles.

The fox and the hound must agree on the radio group, so it is defined here and
imported by both. This module is copied to BOTH boards -- see AGENTS.md
section 5.

Pick a group that nothing else nearby is using. 0 is the MicroPython default,
so any micro:bit whose radio was switched on without configuring a group will
be sitting on it; 42 is the value most tutorials use. Both invite collisions
with other kit in the room.
"""

RADIO_GROUP = 16
