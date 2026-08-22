# Brand Position

Codified in `brandops/brand.py`. Change it there and the whole engine changes
with it -- triage, scoring, hooks, copy and measurement all resolve back to
these definitions.

## The white space

Every private school claims excellence, tradition, leadership, opportunity,
community and college preparation. Those words are not wrong; they are
invisible. Our territory is the intersection nobody else can assemble
authentically:

> **Known personally · challenged seriously · formed intentionally · grounded in
> Catholicism · surrounded by community · prepared for meaningful outcomes.**

## The six pillars

Each pillar carries a promise, an evidence test, and a target share of published
volume. The evidence test is the question an editor asks of an asset before
claiming the pillar. If the answer is no, it is not that pillar -- no matter what
the caption says.

| Pillar | Parent promise | Evidence test | Share |
| --- | --- | --- | --- |
| **Known & Safe** | My child will be known here. He will not disappear. | Can a parent see an adult paying attention to one specific student? | 15% |
| **Challenged to Grow** | The work here is real and my child will be pushed. | Would a skeptical parent call this academically serious without a caption? | 20% |
| **Formation & Character** | Not simply preparing them for what comes next. Forming them for it. | Does this show a young person becoming capable, not merely busy? | 15% |
| **Catholic Identity** | The faith is lived here, not decorated with. | Is faith being lived in this frame, or merely present in it? | 15% |
| **Belonging & Community** | My child will have people here. | Could a 13-year-old picture himself inside this frame? | 20% |
| **Outcomes** | This tuition buys a documented return. | Is there a specific, checkable fact here -- a name, a number, a place? | 15% |

Run `python -c "from brandops.brand import proof_prompt, Pillar; print(proof_prompt(Pillar.KNOWN))"`
to get the shot list that proves any pillar.

## Language discipline

The engine refuses copy containing institutional filler. Each banned phrase maps
to what must replace it -- a specific, observable fact:

| Instead of | Do this |
| --- | --- |
| "academic excellence" | name the course, the assignment, or the score |
| "preparing tomorrow's leaders" | name one graduate and what he leads now |
| "well-rounded" | name the two specific things this student does |
| "faith-based education" | show one thing the faith actually changed today |
| "state-of-the-art" | show the equipment being used, and by whom |
| "nurturing environment" | show one adult noticing one student |

```bash
python -m brandops lint "Our commitment to academic excellence..."
```

Clickbait is refused on the same basis. A school that overclaims once spends the
next year being discounted. Credibility is the asset being built.

## Creative intelligence: study the mechanism, never the creative

Watch what works for independent schools, boarding schools, universities, test
prep, youth sports academies, summer camps and every other category selling
parents a better future for their child. Do not copy their creative. Ask:

1. What is the psychological mechanism? (relief? status? fear? belonging?)
2. Does St. Mary's have an **authentic** version of that story?
3. What evidence would we need to film to tell it honestly?

Then separate what you observed from what you concluded. "Their reels with a
single student voice get more comments" is evidence. "Single-voice reels work
because parents trust students more than administrators" is inference. Label it
as such and test it before building a quarter on it.

## Athletics

Athletics photographs well, fills a calendar and delivers real proof of
discipline, teamwork and community. It is also the fastest way to accidentally
become "the sports school" in the market's mind. The mix report enforces a hard
cap at 25% of published volume (`brandops/mix.py`), and answers the objection
"isn't this mostly an athletics school?" with the classroom rather than with a
defense of athletics.
