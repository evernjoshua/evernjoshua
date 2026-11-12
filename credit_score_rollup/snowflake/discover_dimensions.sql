-- ---------------------------------------------------------------------------
-- discover_dimensions.sql - run this FIRST.
--
-- Lists the AcqSource / Branding / Fee combinations the BAU query actually
-- produces, with how many accounts booked under each, so you can fill in the
-- name_map in vcr_actuals.sql against real values rather than guesses.
--
-- The heat map needs a name for every product that has a roll-up tab. Anything
-- here with a meaningful number of boards and no name in the map will simply
-- not get actuals - that is the gap check_actuals.py reports.
-- ---------------------------------------------------------------------------

SET reporting_start_date = '2023-01-01';
SET reporting_end_date   = '2026-10-31';

SELECT
    mb2.acquisition_segment                AS AcqSource,
    mb2.product_name                       AS Branding,
    SUBSTR(mb2.annual_fee_group, 1,
           CHARINDEX('/', mb2.annual_fee_group) - 1)  AS Fee,
    mb2.annual_fee_group                   AS AnnualFeeGroup,
    COUNT(*)                               AS Accounts,
    MIN(mb2.account_open_month_end)        AS FirstOpenMonth,
    MAX(mb2.account_open_month_end)        AS LastOpenMonth
FROM cstone_biz.profit.pti_fact_acquisition mb2
WHERE mb2.account_open_month_end >= '2023-01-01'
  AND mb2.acquisition_channel = 'Digital'
  AND mb2.origination_branding <> 'Secured'
GROUP BY 1, 2, 3, 4
ORDER BY Accounts DESC;
