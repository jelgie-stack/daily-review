# Volume drop: fewer orders than the baseline

The decomposition says orders moved, not the average ticket. That narrows the causes to things
that change how many people buy.

## Checks, in order

1. **Reporting.** Count units with any revenue yesterday vs the same weekday last week. If the
   count fell, it is a feed problem until proven otherwise.
2. **Where did the orders go?** The brief's unit table and channel mix answer this.
   - Concentrated in a few units: go to `unit_drop.md`.
   - Spread evenly across units: something market-wide (weather, holiday, a campaign ending).
   - One channel down, another up: go to `channel_shift.md`; it may be mix, not loss.
3. **New vs returning.** If new customers fell more than total orders, acquisition stalled: check
   paid media spend by day, campaign status, budget caps, tracking breaks. If returning customers
   fell, check CRM sends, loyalty, and app or site availability.
4. **Traffic vs conversion** (if sessions are configured). Fewer sessions is a demand or
   marketing problem; the same sessions with fewer orders is a site, pricing, or availability
   problem. See `conversion_drop.md`.
5. **Time of day** (restaurant profile). The daypart mix table shows whether one daypart
   carried the drop. Lunch-only drops are usually weather or a nearby office change;
   dinner-only drops are usually competition or staffing.

## Deciding

- **Persistent (flag is red):** assign an owner today. Two days of the same move is a change
  in the business, not noise.
- **One-off (flag is orange):** note it and wait a day. Most one-day moves reverse. Say so in
  the brief so nobody over-reacts.
