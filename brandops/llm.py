"""Optional Claude assistance -- and the prompts to use it without paying twice.

Cost discipline first: nothing in this package requires an API key. Every
generator here also renders a paste-ready prompt, so a school already paying
for a chat subscription can run the same step at no additional cost.

When `anthropic` is installed and credentials are present, `Claude.complete()`
calls the Messages API directly. Output still passes through the same copy
lint and the same human approval gate as anything else -- the model drafts, it
never publishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from . import config
from .audiences import Audience
from .brand import BANNED_PHRASES, OPERATING_PRINCIPLE, Pillar
from .platforms import Platform

MODEL = "claude-opus-5"
DEFAULT_EFFORT = "medium"
DEFAULT_MAX_TOKENS = 16000

# The rules that go on every request. The model drafts inside the brand, or it
# is not useful.
BRAND_SYSTEM = f"""You are drafting content for {config.SCHOOL_NAME}, a Catholic high school.

{OPERATING_PRINCIPLE}

Hard rules:
- Never invent a fact. No statistic, name, quote, score, acceptance or outcome
  that was not given to you. If a fact would strengthen the copy and you do not
  have it, write [NEEDS: what is missing] and continue.
- Never use these phrases or their close variants: {', '.join(sorted(BANNED_PHRASES))}.
  Replace each with a specific, observable detail.
- Do not write clickbait. The institution's credibility is the asset.
- Adults do not imitate teenage slang. Student voice belongs to students.
- Prove the pillar with evidence in the frame; do not assert it in adjectives.
- Write plainly. Short sentences. No exclamation points unless a student said it.
"""


@dataclass
class Prompt:
    """A request that can be sent to the API or pasted into a chat window."""

    purpose: str
    system: str
    user: str

    def as_text(self) -> str:
        return f"# {self.purpose}\n\n## System\n{self.system}\n\n## Task\n{self.user}\n"

    def to_dict(self) -> dict[str, Any]:
        return {"purpose": self.purpose, "system": self.system, "user": self.user}


def _pillar_block(pillar: Pillar) -> str:
    spec = pillar.spec
    return (
        f"Pillar: {spec.name}\n"
        f"Promise to parents: {spec.parent_promise}\n"
        f"Promise to students: {spec.student_promise}\n"
        f"Evidence test: {spec.evidence_test}\n"
        f"Proof to look for: {'; '.join(spec.proof[:4])}"
    )


def _audience_block(audience: Audience) -> str:
    spec = audience.spec
    return (
        f"Audience: {spec.name} ({spec.funnel_stage})\n"
        f"Objective: {spec.objective}\n"
        f"They believe it when: {'; '.join(spec.believes_when[:3])}\n"
        f"Emphasize: {', '.join(spec.emphasize[:5])}\n"
        f"Avoid: {', '.join(spec.avoid)}\n"
        f"CTA policy: {spec.cta_policy}"
    )


def caption_prompt(
    *,
    story: str,
    pillar: Pillar,
    audience: Audience,
    platform: Platform,
    facts: Sequence[str] = (),
    quote: str = "",
    draft: str = "",
) -> Prompt:
    spec = platform.spec
    low, high = spec.caption_chars
    known = "\n".join(f"- {f}" for f in facts) or "- (none supplied)"
    task = f"""{_pillar_block(pillar)}

{_audience_block(audience)}

Platform: {spec.name} ({spec.surface})
Voice: {spec.voice}
Caption length: {low}-{high} characters. Hashtags: {spec.hashtags[0]}-{spec.hashtags[1]}.
CTA style: {spec.cta_style}

Story: {story}
Verified facts you may use:
{known}
Student/teacher quote (use verbatim or not at all): {quote or '(none)'}

{'Current draft to improve:' + chr(10) + draft if draft else ''}

Write the caption. Then, on a separate line beginning "MISSING:", list any fact
that would have made it stronger."""
    return Prompt(f"{spec.name} caption", BRAND_SYSTEM, task)


def hook_prompt(*, story: str, pillar: Pillar, audience: Audience, facts: Sequence[str] = ()) -> Prompt:
    known = "\n".join(f"- {f}" for f in facts) or "- (none supplied)"
    task = f"""{_pillar_block(pillar)}

{_audience_block(audience)}

Story: {story}
Verified facts:
{known}

Write five opening hooks for a vertical video. Each must be speakable in under
three seconds and readable as on-screen text. For each, name the structure it
uses (unexpected statement, parent concern, student question, transformation,
curiosity, contradiction, surprising statistic, behind the scenes, emotional
moment, or what-this-actually-looks-like) and state in one clause what the
footage must show for the hook to be honest."""
    return Prompt("Hook options", BRAND_SYSTEM, task)


def ideation_prompt(
    *,
    when: str,
    yesterday: Sequence[str],
    today: Sequence[str],
    this_week: Sequence[str],
    deficits: Sequence[str],
    phase: str,
) -> Prompt:
    def bullets(items: Sequence[str]) -> str:
        return "\n".join(f"- {i}" for i in items) or "- (nothing recorded)"

    task = f"""Date: {when}
Admissions funnel phase: {phase}

What happened yesterday:
{bullets(yesterday)}

What is happening today:
{bullets(today)}

What is happening this week:
{bullets(this_week)}

Brand pillars we are currently underweight on:
{bullets(deficits)}

Produce four sections and nothing else:
TODAY -- the three to five strongest content opportunities, each with the pillar
it proves and the audience it is for.
THIS WEEK -- five to ten stories worth capturing.
MISSING -- pillars or audiences we have neglected, and the specific story that
would fix each.
CAPTURE REQUEST -- exact photographs and video to obtain today, written so a
teacher who knows nothing about marketing can execute it in under ten minutes."""
    return Prompt("Daily ideation", BRAND_SYSTEM, task)


def video_edit_prompt(*, transcript: str, story: str, pillar: Pillar, target_seconds: int = 25) -> Prompt:
    task = f"""{_pillar_block(pillar)}

Story: {story}
Target length: {target_seconds} seconds, vertical.

Transcript with timestamps:
{transcript}

Return:
1. The clips to keep, as timestamp ranges, in the order they should be cut.
2. Any dead footage to drop and why.
3. The single strongest verbatim sentence, with its speaker.
4. Three on-screen hook options for the first frame.
5. What B-roll is needed to cover each cut."""
    return Prompt("Video edit plan", BRAND_SYSTEM, task)


class Claude:
    """Thin wrapper over the Messages API. Degrades to prompt-only if absent."""

    def __init__(self, *, model: str = MODEL, effort: str = DEFAULT_EFFORT) -> None:
        self.model = model
        self.effort = effort
        self._client = None
        self._error = ""
        try:
            import anthropic  # noqa: PLC0415 -- optional dependency by design
        except ImportError:
            self._error = "the `anthropic` package is not installed (pip install anthropic)"
            return
        try:
            self._client = anthropic.Anthropic()
        except Exception as exc:  # credentials missing or malformed
            self._error = f"could not build an Anthropic client: {exc}"

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def unavailable_reason(self) -> str:
        return self._error

    def complete(self, prompt: Prompt, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        """Run a prompt. Raises RuntimeError with the paste-ready text if offline."""
        if not self.available:
            raise RuntimeError(
                f"Claude is not available: {self._error}. "
                "Paste this prompt into the chat subscription the school already pays for:\n\n"
                + prompt.as_text()
            )
        import anthropic  # noqa: PLC0415

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=prompt.system,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                messages=[{"role": "user", "content": prompt.user}],
            )
        except anthropic.NotFoundError as exc:
            raise RuntimeError(f"unknown model {self.model!r}: {exc}") from exc
        except anthropic.RateLimitError as exc:
            retry = exc.response.headers.get("retry-after", "60")
            raise RuntimeError(f"rate limited; retry after {retry}s") from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError(f"could not reach the API: {exc}") from exc

        if response.stop_reason == "refusal":
            raise RuntimeError("the model declined this request")
        return "".join(block.text for block in response.content if block.type == "text").strip()
