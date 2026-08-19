"""Core Seeker -- a v2.0.0-alpha.1 "Vulnerable Core" reference agent.

Experimental/reference only, not a claim of optimal strategy -- see
docs/V2_0_ALPHA_ARCHITECTURE.md Sec 6 and docs/V2_0_ALPHA1_EVALUATION.md
for the research question this agent exists to probe: can a Python
entrant locate and eliminate an opponent's fixed core under
``bytefray-rules-2-alpha1`` using only ordinary ``READ``/``WRITE``, with
no privileged knowledge of where that core actually is?

Strategy, and the constraint it works under:
``Observation`` exposes no opponent state and no ownership map -- the
only way to learn anything about the arena's contents is a ``READ``,
which returns one byte value, not an owner. This agent treats any byte
that is neither the arena's untouched default (``0``) nor its own
signature as "foreign-looking": evidence *something else* wrote there,
without knowing what or whom. One foreign-looking cell alone is treated
as noise (it could be a single incidental write from an opponent's own
ordinary expansion sweep passing through, nowhere near that opponent's
actual core) -- but two foreign-looking hits found within
``LOCK_RADIUS`` of each other are treated as a plausible cluster worth
committing to, since a real core is ``CORE_SIZE`` contiguous cells all
sharing one owner, not an isolated point.

Two modes, cycled by a small state machine:

    SCANNING    -- one action in every ``SCAN_EVERY`` is a ``READ`` at a
                   slowly advancing scan cursor (a stride chosen for good
                   arena coverage, distinct from any bundled starter's
                   stride -- see Hunter's docstring for why sharing a
                   stride with another sweep is a bad idea); the rest are
                   an ordinary outward claiming sweep, so budget spent
                   scanning is never *pure* loss when nothing is found.
    ASSAULTING  -- committed for a fixed burst of actions once a cluster
                   is found: every action for the burst's duration is a
                   ``WRITE`` across a window centered on the detected
                   cluster, sized comfortably larger than ``CORE_SIZE``
                   to tolerate an imprecise anchor guess. No new attack
                   action exists in this Ruleset -- "assault" here is
                   exactly the same ``WRITE`` any other agent uses to
                   claim territory, aimed at a specific, evidence-derived
                   location instead of an outward sweep.

Important state this agent tracks:
- ``last_foreign_address``: the most recent scan hit that did not itself
  trigger a lock-on, so the *next* hit can be compared against it.
- ``mode`` / ``assault_cursor`` / ``assault_remaining``: which phase this
  agent is in, and (while assaulting) where the burst is and how much of
  it is left.
- ``scan_cursor`` / ``expand_cursor``: independent sweep positions for
  scanning and ordinary expansion, so neither interferes with the other's
  coverage.

What you might reasonably change:
- ``LOCK_RADIUS``: a larger value locks on from more widely separated
  hits (more false positives, faster detection); a smaller one requires
  tighter evidence before committing.
- ``ASSAULT_WINDOW``/``ASSAULT_ACTIONS``: a wider burst tolerates a
  worse anchor guess at the cost of more actions per commitment.
"""

from battle_engine.agent_api import ActionKind, AgentAction, MatchContext, Observation

SCAN_EVERY = 3  # 1 action in every 3 scans; the other 2 expand
LOCK_RADIUS = 12  # how close two foreign hits must be to count as one cluster
ASSAULT_WINDOW = 16  # width of the WRITE burst once locked on (> CORE_SIZE)


class CoreSeekerAgent:
    def reset(self, context: MatchContext) -> None:
        self.rng = context.rng  # unused by this strategy, but always available
        self.arena_size = context.arena_size
        self.signature = 0x5E
        self.scan_stride = (int(context.arena_size * 0.381_966_011) | 1) or 1
        self.expand_stride = 149
        self.scan_cursor = context.arena_size // 3
        self.expand_cursor = 0
        self.last_foreign_address: int | None = None
        self.mode = "scan"
        self.assault_cursor = 0
        self.assault_remaining = 0
        self.actions_taken = 0

    def act(self, observation: Observation) -> AgentAction:
        if self.mode == "assault":
            address = self.assault_cursor
            self.assault_cursor = (self.assault_cursor + 1) % self.arena_size
            self.assault_remaining -= 1
            if self.assault_remaining <= 0:
                self.mode = "scan"
                self.last_foreign_address = None
            return AgentAction(ActionKind.WRITE, address, self.signature)

        self.actions_taken += 1
        if self.actions_taken % SCAN_EVERY == 0:
            address = self.scan_cursor
            self.scan_cursor = (self.scan_cursor + self.scan_stride) % self.arena_size
            return AgentAction(ActionKind.READ, address)

        if observation.last_read is not None and self._looks_foreign(observation.last_read):
            hit_address = (self.scan_cursor - self.scan_stride) % self.arena_size
            if self.last_foreign_address is not None and self._within_lock_radius(
                hit_address, self.last_foreign_address
            ):
                self.mode = "assault"
                anchor = min(hit_address, self.last_foreign_address)
                self.assault_cursor = (anchor - ASSAULT_WINDOW // 4) % self.arena_size
                self.assault_remaining = ASSAULT_WINDOW
                self.last_foreign_address = None
            else:
                self.last_foreign_address = hit_address

        address = self.expand_cursor
        self.expand_cursor = (self.expand_cursor + self.expand_stride) % self.arena_size
        return AgentAction(ActionKind.WRITE, address, self.signature)

    def _looks_foreign(self, value: int) -> bool:
        return value != 0 and value != self.signature

    def _within_lock_radius(self, a: int, b: int) -> bool:
        forward = (a - b) % self.arena_size
        backward = (b - a) % self.arena_size
        return min(forward, backward) <= LOCK_RADIUS


def create_agent() -> CoreSeekerAgent:
    return CoreSeekerAgent()
