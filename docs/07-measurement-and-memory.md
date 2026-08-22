# Measurement and Brand Memory

## Metrics that matter

Four tiers, in ascending order of importance:

**Attention** -- three-second retention, completion, watch time, thumb-stop rate.
**Engagement** -- shares, saves, comments. (Reactions and follower counts are
recorded and explicitly labeled as vanity; they never justify a recommendation.)
**Interest** -- profile visits, link clicks, site sessions.
**Admissions behavior** -- inquiries, visit and shadow registrations,
applications started and completed, enrollments.

The last tier is the only one that pays tuition. Where the report finds no
attributed admissions actions, it says so and prescribes the fix (UTM tags, a
landing page per campaign) rather than drawing conclusions from engagement.

```bash
python -m brandops record p1 --platform instagram_reel \
  --pillar known_and_safe --audience prospective_parent \
  --hook parent_concern --format "vertical video" \
  --metric impressions=2100 --metric three_second_views=1300 \
  --metric shares=40 --metric inquiries=3
```

## Benchmarks come from us

There are no industry-average numbers in this system. Medians are computed from
our own history, per platform -- and when a platform has fewer than five
measured posts, the report falls back to the overall median instead, because a
median drawn from three posts is just those three posts and makes everything
look exactly average.

A post's **index** is its performance against our median. 1.0 is typical, 1.4+
is a winner, 0.65 and below is a loser.

## The weekly report

```bash
python -m brandops weekly --learn
```

Sections: winners, losers, **observed evidence**, **strategic inference**, pillar
performance, creative performance, next week, capture assignments.

The two middle sections are kept rigorously apart:

> **OBSERVED EVIDENCE**
> p3 on instagram_reel ran 1.52x our median (hook rate 61.9%, shares 1.9%)
>
> **STRATEGIC INFERENCE (unproven -- test before acting as if settled)**
> the 'parent_concern' hook structure is carrying the openings (n=3) -- run it
> twice more before treating it as a rule

Inference is gated on sample size. With fewer than three observations the report
says "too small to act on" instead of inventing a lesson. This is the single
discipline that stops a marketing department from believing something for a year
because of one good Tuesday.

## Brand memory

Every measured result folds into `data/memory.json`: hook structures, pillars,
platforms, formats and audiences each carry a running mean and a sample count.
Nothing is treated as confident below three observations.

Memory also banks what does not come from analytics: best posts, student
stories, testimonials, statistics (with source and a verified flag), outcomes,
traditions, signature phrases, photography patterns, underused stories, evergreen
assets -- and the **objection library**.

```bash
python -m brandops memory
```

The objection library ships seeded with the questions schools like this one
field ("Is it worth the tuition?", "Will my son be known here?", "Isn't this
mostly an athletics school?", "We're not Catholic -- will he belong?"), each
mapped to the pillar that answers it and the evidence that proves it. **Replace
these with what our admissions office actually hears.** That list is worth more
than everything else in the file, and the system will never confuse a seeded
objection for something it measured -- it reports "no confident performance
history" when it has none.

The point: do not start from zero on Monday. The system should be materially
smarter in March than it was in September.
