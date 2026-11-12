-- ---------------------------------------------------------------------------
-- actuals.sql - produces the actuals.csv the segment heat map reads.
--
-- The heat map joins actuals at ROLL-UP level only. For a row to be used:
--
--   * Branding           must be 'All'
--   * OriginalCreditLine must be 'All'          (both per ACTUALS_ROLLUP_ALL)
--   * segment + ' ' + fee + '_' + Branding must rebuild the roll-up tab name,
--     e.g. 'Credit Karma' + ' ' + '95' + '_' + 'All' -> Credit Karma $95_ALL.
--     Matching ignores case, spaces and the dollar sign, so write the fee as
--     95, not $95. Where there is no fee in the tab name, put 'All' in Fee and
--     the name becomes segment + '_All' -> Google PQ Paid Search_ALL.
--   * mob is 12, 24 or 36 - year 1, 2 and 3 of the heat map.
--
-- Anything at a finer grain than that is ignored, which is deliberate: a single
-- credit-line slice can read 0% or 100% charge-off and wreck the spread.
--
-- TWO THINGS TO EDIT, both marked EDIT below:
--   1. SOURCE   - the vintage/MOB performance table these figures come from.
--   2. name_map - your campaign identifiers against the names above.
-- ---------------------------------------------------------------------------

WITH name_map AS (
    -- EDIT: put your own identifiers in the first two columns. The last two are
    -- what the heat map expects and should not need changing - they were
    -- generated from its ROLLUP_SHEETS, ROLLUP_ONLY and CAMPAIGN_TOTALS.
    SELECT * FROM VALUES
        --  src_partner              src_fee   segment                        fee
        ('<YOUR CODE>',              95,      'Credit Karma',                 '95'),
        ('<YOUR CODE>',              75,      'Credit Karma',                 '75'),
        ('<YOUR CODE>',              39,      'Credit Karma',                 '39'),
        ('<YOUR CODE>',               0,      'Credit Karma',                 '0'),
        ('<YOUR CODE>',            NULL,      'Credit Karma WANDER',          'All'),
        ('<YOUR CODE>',              95,      'Experian',                     '95'),
        ('<YOUR CODE>',              75,      'Experian',                     '75'),
        ('<YOUR CODE>',              39,      'Experian',                     '39'),
        ('<YOUR CODE>',               0,      'Experian',                     '0'),
        ('<YOUR CODE>',            NULL,      'EXPERIAN WANDER',              'All'),
        ('<YOUR CODE>',              75,      'MoneyLion',                    '75'),
        ('<YOUR CODE>',              75,      'MoneyLion DCO',                '75'),
        ('<YOUR CODE>',              39,      'MoneyLion DCO',                '39'),
        ('<YOUR CODE>',              75,      'Credit Sesame',                '75'),
        ('<YOUR CODE>',              39,      'Credit Sesame',                '39'),
        ('<YOUR CODE>',            NULL,      'Credit Sesame X5 and Wander',  'All'),
        ('<YOUR CODE>',              75,      'AMEX DCO',                     '75'),
        ('<YOUR CODE>',              39,      'AMEX DCO',                     '39'),
        ('<YOUR CODE>',               0,      'AMEX DCO',                     '0'),
        ('<YOUR CODE>',              75,      'Organic',                      '75'),
        ('<YOUR CODE>',              39,      'ORGANIC',                      '39'),
        ('<YOUR CODE>',               0,      'ORGANIC',                      '0'),
        ('<YOUR CODE>',            NULL,      'ORGANIC X5 and Wander',        'All'),
        ('<YOUR CODE>',               0,      'Organic Omni',                 '0'),
        ('<YOUR CODE>',            NULL,      'Google PQ Paid Search',        'All'),
        ('<YOUR CODE>',            NULL,      'CREDITCARDS.COM',              'All'),
        ('<YOUR CODE>',              39,      'BrightMoney',                  '39'),
        ('<YOUR CODE>',            NULL,      'Omni',                         'All'),
        ('<YOUR CODE>',            NULL,      'Digital',                      'All')
    AS m (src_partner, src_fee, segment, fee)
),

source AS (
    SELECT
        -- EDIT: the columns on your side of the join.
        v.vintage_month          AS vintage_month,     -- a DATE or YYYY-MM
        v.partner_code           AS src_partner,
        v.annual_fee             AS src_fee,
        v.months_on_book         AS mob,

        -- these keep their names: the heat map reads them by name
        v.boards                      AS boards,
        v.avg_initial_line_per_booked AS avg_initial_line_per_booked,
        v.cum_unit_rate               AS cum_unit_rate,
        v.cum_net_dollar              AS cum_net_dollar,
        v.cumulative_roa              AS cumulative_roa,
        v.cum_pti                     AS cum_pti,
        v.total_actives               AS total_actives,
        v.ending_receivables          AS ending_receivables,
        v.avg_balance_per_active      AS avg_balance_per_active,
        v.cuml_profit_per_booked      AS cuml_profit_per_booked,
        v.cuml_gross_rev_per_booked   AS cuml_gross_rev_per_booked,
        v.thirty_plus_unit            AS thirty_plus_unit,
        v.thirty_plus_doll            AS thirty_plus_doll,
        v.sixty_plus_unit             AS sixty_plus_unit,
        v.sixty_plus_doll             AS sixty_plus_doll
    FROM <YOUR_DB>.<YOUR_SCHEMA>.<VINTAGE_PERFORMANCE> v   -- EDIT: SOURCE
    WHERE v.months_on_book IN (12, 24, 36)
      -- Roll-up grain only. If your table carries its own breakdown flags,
      -- pin them here too so nothing finer leaks in.
      AND v.credit_line_band IS NULL          -- EDIT or drop
)

SELECT
    TO_CHAR(s.vintage_month, 'YYYY-MM')   AS "Vintage",
    m.segment                             AS "segment",
    'All'                                 AS "Branding",
    m.fee                                 AS "Fee",
    'All'                                 AS "OriginalCreditLine",
    s.mob                                 AS "mob",
    s.total_actives                       AS "TotalActives",
    s.ending_receivables                  AS "EndingReceivables",
    s.cuml_profit_per_booked              AS "CumlProfitPerBooked",
    s.cuml_gross_rev_per_booked           AS "CumlGrossRevPerBooked",
    s.thirty_plus_unit                    AS "ThirtyPlusUnit",
    s.thirty_plus_doll                    AS "ThirtyPlusDoll",
    s.sixty_plus_unit                     AS "SixtyPlusUnit",
    s.sixty_plus_doll                     AS "SixtyPlusDoll",
    s.cum_unit_rate                       AS "CumUnitRate",
    s.cum_net_dollar                      AS "CumNetDollar",
    s.cumulative_roa                      AS "CumulativeROA",
    s.avg_balance_per_active              AS "Avg_BalancePerActive",
    s.avg_initial_line_per_booked         AS "Avg_InitialLinePerBooked",
    s.boards                              AS "Boards",
    s.cum_pti                             AS "CumPTI"
FROM source s
JOIN name_map m
  ON m.src_partner = s.src_partner
 AND (m.src_fee = s.src_fee OR (m.src_fee IS NULL AND m.fee = 'All'))
ORDER BY m.segment, m.fee, s.mob, "Vintage";

-- ---------------------------------------------------------------------------
-- IF YOUR TABLE IS FINER THAN ROLL-UP GRAIN and you have to aggregate, do NOT
-- average the rates. CumUnitRate, CumNetDollar and CumulativeROA are ratios:
-- averaging them across slices weights a 200-account slice like a 40,000-account
-- one. Re-derive each from its own numerator and denominator, e.g.
--
--     SUM(units_charged_off) / NULLIF(SUM(boards), 0)        AS "CumUnitRate",
--     SUM(net_charge_off_dollars) / NULLIF(SUM(orig_rcv), 0) AS "CumNetDollar",
--     SUM(pre_tax_income) / NULLIF(SUM(avg_receivables), 0)  AS "CumulativeROA",
--     SUM(boards)                                            AS "Boards",
--     SUM(initial_line) / NULLIF(SUM(boards), 0)  AS "Avg_InitialLinePerBooked"
--
-- grouped by vintage_month, segment, fee, mob.
-- ---------------------------------------------------------------------------
