# The method

Most "daily dashboards" fail the same way: they show every number, compare it to yesterday or
to a monthly average, and leave the reader to decide what matters. By week three nobody opens
them. This review was built around the opposite idea: show only what changed, prove it changed,
say why, and say what to do.

## 1. Same-weekday baselines

Businesses have a weekly rhythm. Friday is not Tuesday. Comparing yesterday to the day before,
or to a 28-day average, produces a "drop" every Monday and a "spike" every Saturday. So every
number is compared to the **median of the trailing eight occurrences of the same weekday**.

Eight is a compromise: enough to be stable, short enough that a step change (new units, a
price increase, a season turning) rolls through in two months. `rules.baseline_weeks` changes
it.

## 2. Robust statistics

The baseline uses the **median**, and spread is measured with the **median absolute deviation
(MAD)**, scaled by 1.4826 so it reads like a standard deviation. One freak day in the baseline
window (a holiday, an outage) does not drag the average or inflate the spread the way a mean
and standard deviation would. When MAD is zero (eight identical days, which happens with tiny
units), the engine falls back to the standard deviation.

A **z-score** of 2 or more is the default bar for "this is unusual". That alone is not enough.

## 3. Floors

Statistical significance is not business significance. A unit that does $300 a day can be
three standard deviations down on $90. So every flag also has to clear a **currency floor**:
`min_signal_revenue` for the top line, `unit_move_abs` for a unit. Set the floors to the
smallest move a human would act on. This is the single most important tuning step; the brief
is only as good as its floors.

## 4. Decomposition

Revenue = orders × average order value. A revenue move is split exactly:

```
volume_effect = (orders - base_orders) * base_aov
value_effect  = orders * (aov - base_aov)
revenue - base_revenue = volume_effect + value_effect
```

Fewer orders and a smaller ticket are different problems with different owners (marketing
and operations vs pricing and merchandising), so the brief names the driver in the first
line of every revenue flag. When AOV rises enough to hide a volume drop in the revenue line,
the engine flags the volume drop anyway; that case is where the most expensive mistakes
hide.

The ecommerce profile adds orders = sessions × conversion for the same reason.

## 5. Persistence

A single soft day is usually noise, weather, or a calendar effect. The brief computes the
revenue z-score for each of the last three days against each day's own baseline. If today is
beyond the threshold **and** at least two of the three days point the same way (|z| ≥ 1), the
move is called a trend and the flag is red. Otherwise it is orange: noted, not actioned.

Unit-level moves use a simpler version: was the same unit down yesterday too?

## 6. Separating lumpy segments

Catering, wholesale, B2B, events: one large order looks like a 30% day for a small unit. The
restaurant profile moves catering out of the core numbers and reports it on its own line.
Any profile can declare such a segment; it only needs a SQL predicate in `config.filters`.

## 7. Holidays

A holiday is not a bad weekday, and the day after one is not a recovery. Three things happen:

- **Baselines skip holidays.** The same-weekday window drops any date that is a holiday or a
  marked neighbour (the day before Thanksgiving, the day after Christmas) and reaches further
  back to keep eight clean observations. Without this, the eight Thursdays after Thanksgiving
  all carry a 20% day in their baseline and read as strong.
- **A holiday is compared to the same holiday last year**, matched by rule rather than by
  counting back 364 days. That distinction matters for fixed-date holidays: 364 days before
  July 4, 2026 (a Saturday) is July 5, 2025. The trend check is suspended on holidays, so a
  holiday never starts or extends a "three-day slump".
- **Holiday weeks are marked in the trend table**, so a dip in the 13-week view explains itself.

The default calendar is US (`profiles/holidays.yaml`), expressed as rules (fixed dates, "4th
Thursday of November", Easter offsets) so it works for any year. Add your own holidays, local
events, or a different country's calendar in `config.yaml` under `holidays:`.

## 8. One verdict, then flags, then tables

The brief's first line is a sentence a chief executive can read without the rest. Then the
flags, each with a playbook. Then the evidence, for anyone who wants it. The order is the
point: the reader who stops after one line still knows whether to worry.

## What it deliberately does not do

- **No weather or event feed.** A rainy Tuesday looks like a soft Tuesday. The playbooks tell
  the reader to check weather first; the engine does not.
- **No forecasting.** Baselines are descriptive. Forecasts belong somewhere else.
- **No root cause from data alone.** The playbooks are checklists for a person (or an agent
  with tools). The engine finds the where and the how much; the why needs context.
