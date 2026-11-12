-- ---------------------------------------------------------------------------
-- vcr_actuals.sql - the BAU VCR query, turned into the actuals.csv the heat map
-- reads. Every VCR attribute and measure is carried through.
--
-- THREE THINGS THIS DOES THAT THE BAU QUERY DOES NOT:
--
-- 1. WIDENS THE REPORTING WINDOW. The heat map wants figures CUMULATIVE to MOB
--    12, 24 and 36. A cumulative figure needs every month from the account's
--    first through its twelfth, so a nine-month reporting window cannot produce
--    one - it would only catch whichever MOBs happen to land inside it. The
--    window below spans the whole book, from the earliest account open month.
--
-- 2. CUMULATES THE FLOWS AND NOT THE STOCKS. Charge-offs, revenue, expenses and
--    fees are things that happen in a month, so they are summed from MOB 1.
--    Receivables, active counts, buckets and reserves are balances, so they are
--    taken AS AT that MOB. Summing a balance over months would be meaningless.
--
-- 3. COLLAPSES TO ROLL-UP GRAIN. The heat map only joins rows where Branding and
--    OriginalCreditLine are both 'All' - a single credit-line slice can read 0%
--    or 100% charge-off and wreck the spread - and builds its key as
--    segment + ' ' + Fee + '_' + Branding.
--
-- EDIT: the name_map CTE, mapping your AcqSource / Branding / Fee to the names
-- the heat map expects. Run discover_dimensions.sql first to see your values.
-- CONFIRM: the three rate definitions in the rates block near the end.
-- ---------------------------------------------------------------------------

-- was 2026-01-01 / 2026-09-30; widened per note 1 above
SET reporting_start_date = '2023-01-01';
SET reporting_end_date   = '2026-10-31';

WITH acq_agg AS (
   SELECT
       -- account_number_hk,
       mb2.credit_account_id,
       mb2.acquisition_vintage,
       mb2.account_open_month_end,
       mb2.acquisition_channel,
       mb2.acquisition_targeting_type,
       mb2.acquisition_segment,
       mb2.original_card_network,
       mb2.product_name,
        CASE 
            WHEN mb2.application_credit_score IS NULL OR mb2.application_credit_score < 1 THEN COALESCE(TRY_CAST(lbr.credit_score AS INT), -1)
            ELSE mb2.application_credit_score
            END AS application_credit_score,
        case 
            when (mb2.application_credit_score <= 600 or mb2.application_credit_score is null) then '<=600'
            when mb2.application_credit_score between 601 and 639 then '601-639'
            when mb2.application_credit_score >= 640 then '640+'
                end as VantageRange,
       mb2.annual_fee_group,
       SUBSTR(mb2.annual_fee_group,1,(CHARINDEX('/',mb2.annual_fee_group)-1)) AS fee,
       mb2.acquisition_first_second,
       mb2.acquisition_credit_line,
       mb2.purchase_apr,
       CASE WHEN mb2.original_portfolio_id BETWEEN 30 AND 39 THEN 1 ELSE 0 END AS retained_flag
   FROM cstone_biz.profit.pti_fact_acquisition mb2
   /*from MAP logic to get credit_Score in case application_credit_score IS NULL OR application_credit_score < 1*/
    LEFT JOIN (select distinct reservation_number, application_number from cstone_biz.risk.v_los_card_application) lca
        ON mb2.reservation_number = lca.reservation_number
    LEFT JOIN cstone_biz.risk.v_los_bureau_report lbr
        ON lca.application_number = lbr.application_number
   /* MAP Logic End*/   
   WHERE account_open_month_end >= '2023-01-01' and acquisition_channel = 'Digital' and origination_branding <> 'Secured'
),
financials_agg AS (
   SELECT
       reporting_date,
       month_on_book,
       account_number_hk,
       MAX(credit_account_id) AS credit_account_id,
       SUM(new_account_indicator) AS new_account_indicator,
       SUM(ending_receivable) AS ending_receivable,
       SUM(active_card_indicator) AS active_card_indicator,
       SUM(principal_receivable) AS principal_receivable,
       SUM(charge_off_flag) AS charge_off_flag,
       SUM(charge_off_fraud_count) as charge_off_fraud_count,
       SUM(unwind_flag) as unwind_flag,
       SUM(inactive_card_indicator) AS inactive_card_indicator,
       SUM(charge_off_principal_amount) AS charge_off_principal_amount,
       SUM(charge_off_total_amount) AS charge_off_total_amount,
       SUM(late_fee_accrued_amount) AS late_fee_accrued_amount,
       SUM(fee_cash_advance_amount) AS fee_cash_advance_amount,
       SUM(active_credit_line) AS active_credit_line,
       SUM(charge_off_fraud_amount) as fraudamount,
       SUM(CASE WHEN charge_off_code = 52 THEN charge_off_principal_amount ELSE 0 END) AS fraudnetamount52,
       SUM(CASE WHEN charge_off_code = 88 THEN charge_off_total_amount ELSE 0 END) AS fraudgrossamount88,
       SUM(CASE WHEN opening_receivable > 0 AND external_status_reason_code = 'C' AND ending_receivable <= 0 AND status_reason_code NOT IN ('24','25','26','91') THEN 1 ELSE 0 END) AS attrition
   FROM cstone_biz.profit.pti_fact_card_monthly
   WHERE reporting_date BETWEEN $reporting_start_date AND $reporting_end_date
   AND month_on_book <= 44
   GROUP BY reporting_date, month_on_book, account_number_hk
),
fpd_acct AS (
   SELECT
       credit_account_id,
       fpd_mob,
       fpd_flag,
       fpd_cycle
   FROM db_risk.finance_acq_sbx.pti_fpd
   WHERE fpd_cycle = 1
),
bucket_agg AS(
   SELECT
       reporting_date,
       months_on_book,
       credit_account_id,
       SUM(CASE WHEN late_fee_accrued_count = 1 AND total_current_bucket_count = 1 THEN 1 ELSE 0 END) AS current_account_late_fee,
       SUM(CASE WHEN credit_line_increase_indicator = 1 AND fee_credit_line_increase_misc_amount = 0 THEN 1 ELSE 0 END) AS free_cli,
       SUM(total_current_bucket_count) AS total_current_bucket_count,
       SUM(bucket_5_count) AS bucket_5_count,
       SUM(bucket_30_count) AS bucket_30_count,
       SUM(bucket_60_count) AS bucket_60_count,
       SUM(bucket_90_count) AS bucket_90_count,
       SUM(bucket_120_count) AS bucket_120_count,
       SUM(bucket_150_count) AS bucket_150_count,
       SUM(bucket_180_count) AS bucket_180_count,
       SUM(CASE WHEN bucket_90_amount > 0 THEN principal_receivable ELSE 0 END) AS bucket_90_principal_amount,
       SUM(CASE WHEN bucket_120_amount > 0 THEN principal_receivable ELSE 0 END) AS bucket_120_principal_amount,
       SUM(CASE WHEN bucket_150_amount > 0 THEN principal_receivable ELSE 0 END) AS bucket_150_principal_amount,
       SUM(CASE WHEN bucket_180_amount > 0 THEN principal_receivable ELSE 0 END) AS bucket_180_principal_amount,
       SUM(total_current_bucket_amount) AS total_current_bucket_amount,
       SUM(bucket_5_amount) AS bucket_5_amount,
       SUM(bucket_30_amount) AS bucket_30_amount,
       SUM(bucket_60_amount) AS bucket_60_amount,
       SUM(bucket_90_amount) AS bucket_90_amount,
       SUM(bucket_120_amount) AS bucket_120_amount,
       SUM(bucket_150_amount) AS bucket_150_amount,
       SUM(bucket_180_amount) AS bucket_180_amount,
       SUM(ace2_score) AS ace2_score,
       SUM(ace4_score) AS ace4_score,
       SUM(vantage_3_score) AS vantage_3_score,
       SUM(ace2_score_indicator) AS ace2_score_indicator,
       SUM(ace4_score_indicator) AS ace4_score_indicator,
       SUM(vantage_3_score_indicator) AS vantage_3_score_indicator,
       SUM(fee_misc_accrued_total_amount) AS fee_misc_accrued_total_amount,
       SUM(fee_enrollment_amount) AS fee_enrollment_amount,
       SUM(fee_overlimit_amount) AS fee_overlimit_amount,
       SUM(fee_credit_protection_count) AS fee_credit_protection_count,
       SUM(credit_line_increase_indicator) AS credit_line_increase_indicator,
       SUM(fee_credit_line_increase_misc_count) AS fee_credit_line_increase_misc_count,
       SUM(fee_direct_check_count) AS fee_direct_check_count,
       SUM(late_fee_accrued_count) AS late_fee_accrued_count,
       SUM(fee_annual_due_monthly_amount) AS fee_annual_due_monthly_amount,
       SUM(fee_annual_membership_amount) AS fee_annual_membership_amount,
       SUM(fee_duplicate_statement_amount) AS fee_duplicate_statement_amount,
       SUM(fee_fedex_amount) AS fee_fedex_amount,
       SUM(fee_finance_charge_amount) AS fee_finance_charge_amount,
       SUM(late_fee_amount) AS late_fee_amount,
       SUM(fee_replacement_amount) AS fee_replacement_amount,
       SUM(fee_replacement_manual_amount) AS fee_replacement_manual_amount,
       SUM(fee_sales_slip_amount) AS fee_sales_slip_amount,
       SUM(fee_overlimit_adjustment_amount) AS fee_overlimit_adjustment_amount
   FROM cstone_biz.card.fact_card_monthly
   WHERE reporting_date BETWEEN $reporting_start_date AND $reporting_end_date
   AND months_on_book <= 44
   GROUP BY reporting_date, months_on_book, credit_account_id
),
profit_agg AS (
   SELECT
       reporting_date,
       month_on_book,
       account_number_hk,
       MAX(credit_account_id) AS credit_account_id,
       SUM(interest_amount) AS interest_amount,
       SUM(total_rewards) AS total_rewards,
       SUM(fraud_loss_expense) AS fraud_loss_expense,
       SUM(recovery_amount) AS recovery_amount,
       SUM(credit_protection_amount) AS credit_protection_amount,
       SUM(abs(interchange_fee_amount)) AS interchange_fee_amount,
       SUM(fee_reversals) AS fee_reversals,
       SUM(provision_expense) AS provision_expense,
       SUM(sixty_plus_collections_expense) AS sixty_plus_collections_expense,
       SUM(pre_call_and_5_30_collections_expense) AS pre_call_and_5_30_collections_expense,
       SUM(credit_protection_expense) AS credit_protection_expense,
       SUM(customer_service_expense) AS customer_service_expense,
       SUM(booking_expense) AS booking_expense,
       SUM(other_overhead_expense) AS other_overhead_expense,
       SUM(systems_expense) AS systems_expense,
       SUM(recovery_expense) AS recovery_expense,
       SUM(gross_revenue) AS gross_revenue,
       SUM(net_revenue) AS net_revenue
   FROM cstone_biz.profit.pti_fact_profit
   WHERE reporting_date BETWEEN $reporting_start_date AND $reporting_end_date
   AND month_on_book <= 44
   GROUP BY reporting_date, month_on_book, account_number_hk
),
cashflow_agg AS (
   SELECT
       reporting_date,
       account_number_hk,
       MAX(credit_account_id) AS credit_account_id,
       SUM(cash_inflow_amount) AS cash_inflow_amount,
       SUM(cash_outflow_amount) + SUM(total_account_cost_of_funds_amount) as cash_outflow_amount,
       (SUM(cash_inflow_amount) - (SUM(cash_outflow_amount) + SUM(total_account_cost_of_funds_amount))) AS net_cashflow,
       SUM(total_account_cost_of_funds_amount) as total_account_cost_of_funds_amount
   FROM DB_RISK.RISK_SBX.FACT_ACCOUNT_CASHFLOW_SBX
   WHERE reporting_date BETWEEN $reporting_start_date AND $reporting_end_date
   AND ACCOUNT_OPEN_MONTH >= '2023-01-01'
   GROUP BY reporting_date, account_number_hk
),
metrics_agg AS (
   SELECT
       reporting_date,
       month_on_book,
       account_number_hk,
       MAX(credit_account_id) AS credit_account_id,
       SUM(total_sales_net_amount) AS total_sales_net_amount,
       SUM(annual_fee_amount) AS annual_fee_amount,
       SUM(express_pay_fee_amount) AS express_pay_fee_amount,
       SUM(credit_line_increase_fee_amount) AS credit_line_increase_fee_amount,
       SUM(cash_advance_convenience_amount) AS cash_advance_convenience_amount,
       SUM(total_payments_net_amount) AS total_payments_net_amount,
       SUM(authorized_user_fee_amount + premium_card_fee_amount) AS misc_fee_amount
   FROM cstone_biz.profit.pti_metrics
   WHERE reporting_date BETWEEN $reporting_start_date AND $reporting_end_date
   AND month_on_book <= 44
   GROUP BY reporting_date, month_on_book, account_number_hk
),
reserve_agg AS (
   SELECT
       reporting_date,
       month_on_book,
       account_number_hk,
       MAX(credit_account_id) AS credit_account_id,
       SUM(reserve_balance_gross_amount_2) AS reserve_balance_gross_amount_2,
       SUM(reserve_balance_gross_amount_4) AS reserve_balance_gross_amount_4,
       SUM(required_reserve) AS required_reserve
   FROM cstone_biz.profit.pti_fact_reserve
   WHERE reporting_date BETWEEN $reporting_start_date AND $reporting_end_date
   AND month_on_book <= 44
   GROUP BY reporting_date, month_on_book, account_number_hk
),

-- ---------------------------------------------------------------------------
-- EDIT: your identifiers on the left, the heat map's names on the right. A NULL
-- on the left matches anything. Write the fee as 95, not $95: the heat map
-- ignores the dollar sign when it matches. Where a roll-up tab carries no fee,
-- put 'All' in fee_label and the name becomes segment + '_All'.
-- The right-hand side was generated from the notebook's ROLLUP_SHEETS,
-- ROLLUP_ONLY and CAMPAIGN_TOTALS and should not need changing.
-- ---------------------------------------------------------------------------
name_map AS (
    SELECT * FROM VALUES
        --  src_acq_source      src_branding   src_fee   segment                       fee_label
        ('<ACQ SOURCE>',        NULL,          '95',     'Credit Karma',               '95'),
        ('<ACQ SOURCE>',        NULL,          '75',     'Credit Karma',               '75'),
        ('<ACQ SOURCE>',        NULL,          '39',     'Credit Karma',               '39'),
        ('<ACQ SOURCE>',        NULL,          '0',      'Credit Karma',               '0'),
        ('<ACQ SOURCE>',        '<WANDER>',    NULL,     'Credit Karma WANDER',        'All'),
        ('<ACQ SOURCE>',        NULL,          '95',     'Experian',                   '95'),
        ('<ACQ SOURCE>',        NULL,          '75',     'Experian',                   '75'),
        ('<ACQ SOURCE>',        NULL,          '39',     'Experian',                   '39'),
        ('<ACQ SOURCE>',        NULL,          '0',      'Experian',                   '0'),
        ('<ACQ SOURCE>',        '<WANDER>',    NULL,     'EXPERIAN WANDER',            'All'),
        ('<ACQ SOURCE>',        NULL,          '75',     'MoneyLion',                  '75'),
        ('<ACQ SOURCE>',        NULL,          '75',     'MoneyLion DCO',              '75'),
        ('<ACQ SOURCE>',        NULL,          '39',     'MoneyLion DCO',              '39'),
        ('<ACQ SOURCE>',        NULL,          '75',     'Credit Sesame',              '75'),
        ('<ACQ SOURCE>',        NULL,          '39',     'Credit Sesame',              '39'),
        ('<ACQ SOURCE>',        '<WANDER>',    NULL,     'Credit Sesame X5 and Wander','All'),
        ('<ACQ SOURCE>',        NULL,          '75',     'AMEX DCO',                   '75'),
        ('<ACQ SOURCE>',        NULL,          '39',     'AMEX DCO',                   '39'),
        ('<ACQ SOURCE>',        NULL,          '0',      'AMEX DCO',                   '0'),
        ('<ACQ SOURCE>',        NULL,          '75',     'Organic',                    '75'),
        ('<ACQ SOURCE>',        NULL,          '39',     'ORGANIC',                    '39'),
        ('<ACQ SOURCE>',        NULL,          '0',      'ORGANIC',                    '0'),
        ('<ACQ SOURCE>',        '<WANDER>',    NULL,     'ORGANIC X5 and Wander',      'All'),
        ('<ACQ SOURCE>',        '<OMNI>',      '0',      'Organic Omni',               '0'),
        ('<ACQ SOURCE>',        NULL,          NULL,     'Google PQ Paid Search',      'All'),
        ('<ACQ SOURCE>',        NULL,          NULL,     'CREDITCARDS.COM',            'All'),
        ('<ACQ SOURCE>',        NULL,          '39',     'BrightMoney',                '39'),
        ('<ACQ SOURCE>',        '<OMNI>',      NULL,     'Omni',                       'All')
    AS m (src_acq_source, src_branding, src_fee, segment, fee_label)
),

vcr AS (
    -- the BAU query's own SELECT and GROUP BY, unchanged
SELECT
   acq.acquisition_vintage AS Vintage,
   acq.account_open_month_end AS VintageDate,
   f.month_on_book AS MonthsOnBooks,
   acq.acquisition_first_second AS AccountNumber,
   acq.product_name AS Branding,
   acq.acquisition_targeting_type AS Acquisitions,
   acq.original_card_network AS Association,
   acq.acquisition_segment AS AcqSource,
   acq.acquisition_channel AS Subchannel,
   acq.annual_fee_group AS AnnualFeeGroup,
   acq.fee AS Fee,
   acq.acquisition_credit_line AS OriginalCreditLine,
   acq.VantageRange,
   SUM(f.new_account_indicator) AS NewAccounts,
   SUM(p.interest_amount) AS TotalFinanceCharges,
   SUM(f.ending_receivable) AS EndingReceivable,
   SUM(p.total_rewards) AS RewardsAmount,
   SUM(m.total_sales_net_amount) AS TotalNetSales,
   SUM(m.annual_fee_amount) AS FeeAnnualChargeAmount,
   SUM(b.total_current_bucket_count) AS Bucket0Count,
   SUM(b.bucket_5_count) AS Bucket5Count,
   SUM(b.bucket_30_count) AS Bucket30Count,
   SUM(b.bucket_60_count) AS Bucket60Count,
   SUM(b.bucket_90_count) AS Bucket90Count,
   SUM(b.bucket_120_count) AS Bucket120Count,
   SUM(b.bucket_150_count) AS Bucket150Count,
   SUM(b.bucket_180_count) AS Bucket180Count,
   SUM(b.bucket_90_principal_amount) AS Bucket90PrincipalAmount,
   SUM(b.bucket_120_principal_amount) AS Bucket120PrincipalAmount,
   SUM(b.bucket_150_principal_amount) AS Bucket150PrincipalAmount,
   SUM(b.bucket_180_principal_amount) AS Bucket180PrincipalAmount,
   SUM(b.total_current_bucket_amount) AS Bucket0Amount,
   SUM(b.bucket_5_amount) AS Bucket5Amount,
   SUM(b.bucket_30_amount) AS Bucket30Amount,
   SUM(b.bucket_60_amount) AS Bucket60Amount,
   SUM(b.bucket_90_amount) AS Bucket90Amount,
   SUM(b.bucket_120_amount) AS Bucket120Amount,
   SUM(b.bucket_150_amount) AS Bucket150Amount,
   SUM(b.bucket_180_amount) AS Bucket180Amount,
   SUM(f.charge_off_flag) AS ChargeOffIndicator,
   SUM(f.charge_off_fraud_count) AS FraudCount,
   SUM(f.unwind_flag) AS UnwindCount,
   SUM(b.ace2_score) AS ACE2Score,
   SUM(b.ace4_score) AS ACE4Score,
   SUM(b.vantage_3_score) AS Vantage3score,
   SUM(b.ace2_score_indicator) AS ACE2ScoreIndicator,
   SUM(b.ace4_score_indicator) AS ACE4ScoreIndicator,
   SUM(f.active_card_indicator) AS ActiveAccountIndicator,
   SUM(f.inactive_card_indicator) AS InactiveAccountIndicator,
   SUM(f.principal_receivable) AS PrincipalReceivable,
   SUM(p.fraud_loss_expense) AS FraudLossAmount,
   SUM(f.fraudamount) AS FraudAmount,
   SUM(f.fraudnetamount52) AS FraudNetAmount52,
   SUM(f.fraudgrossamount88) AS FraudGrossAmount88,
   SUM(f.charge_off_principal_amount) AS ChargeOffPrincipalAmount,
   SUM(f.charge_off_total_amount) AS ChargeOffAmount,
   SUM(p.recovery_amount) AS RecoveriesAmount,
   SUM(p.credit_protection_amount) AS CreditProtectionAmount,
   SUM(f.late_fee_accrued_amount) AS FeeLateAccruedAmount,
   SUM(p.interchange_fee_amount) AS InterchangeRevenue,
   SUM(m.express_pay_fee_amount) AS FeeDirectCheckAmount,
   SUM(f.fee_cash_advance_amount) AS FeeCashAdvanceAmount,
   SUM(m.credit_line_increase_fee_amount) AS FeeCrLineIncreaseMiscAmt,
   SUM(p.fee_reversals) AS TotalFeeAdjustments,
   SUM(f.active_credit_line) AS ActiveCreditLine,
   SUM(b.fee_misc_accrued_total_amount) AS FeeMiscAccruedTtlAmt,
   SUM(b.fee_enrollment_amount) AS FeeEnrollmentAmount,
   SUM(b.fee_overlimit_amount) AS FeeOverlimitAmount,
   SUM(r.reserve_balance_gross_amount_2) AS ReserveBalGrossAmount2,
   SUM(r.reserve_balance_gross_amount_4) AS ReserveBalGrossAmount4,
   SUM(r.required_reserve) AS RequiredReserves,
   SUM(p.provision_expense) AS ProvisionExpense,
   SUM(p.sixty_plus_collections_expense) AS CollectionsExpense60Plus,
   SUM(p.pre_call_and_5_30_collections_expense) AS CollectionsExpensePreCalland530,
   SUM(c.total_account_cost_of_funds_amount) AS CostofFundsExpense,
   SUM(p.credit_protection_expense) AS CreditProtectionExpense,
   SUM(p.customer_service_expense) AS CustomerServiceExpense,
   SUM(p.booking_expense) AS OneTimeBookingExpense,
   SUM(p.other_overhead_expense) AS OtherOverheadExpense,
   SUM(p.systems_expense) AS SystemsExpense,
   SUM(m.total_payments_net_amount) AS TotalNetPayments,
   SUM(b.vantage_3_score_indicator) AS Vantage3ScoreIndicator,
   SUM(m.cash_advance_convenience_amount) AS TotalCashAdvances,
   SUM(b.fee_credit_protection_count) AS FeeCreditProtectionCount,
   SUM(b.credit_line_increase_indicator) AS CreditLineIncreaseIndicator,
   SUM(b.fee_credit_line_increase_misc_count) AS FeeCrLineIncreaseMiscCnt,
   SUM(b.free_cli) AS FreeCLI,
   SUM(b.fee_direct_check_count) AS FeeDirectCheckCount,
   SUM(b.late_fee_accrued_count) AS FeeLateAccruedCount,
   SUM(b.current_account_late_fee) AS CurrentAccountLateFee,
   SUM(f.attrition) AS Attrition,
   SUM(acq.retained_flag) AS RetainedFlag,
   SUM(b.fee_annual_due_monthly_amount) AS FeeAnnualDueMonthlyAmount,
   SUM(b.fee_annual_membership_amount) AS FeeAnnualMembershipAmount,
   SUM(b.fee_duplicate_statement_amount) AS FeeDuplicateStatementAmount,
   SUM(b.fee_fedex_amount) AS FeeFedExAmount,
   SUM(b.fee_finance_charge_amount) AS FeeFinanceChargeAmount,
   SUM(b.late_fee_amount) AS FeeLateAmount,
   SUM(b.fee_replacement_amount) AS FeeReplacementAmount,
   SUM(b.fee_replacement_manual_amount) AS FeeReplacementManualAmount,
   SUM(b.fee_sales_slip_amount) AS FeeSalesSlipAmount,
   SUM(b.fee_overlimit_adjustment_amount) AS FeeOverlimitAdjustmentAmount,
   SUM(m.misc_fee_amount) AS MiscFeeamount,
   COALESCE(SUM(fd.fpd_flag), 0) AS FPDCount,
   COALESCE(SUM(fd.fpd_cycle), 0) AS FPDEval,
   SUM(p.recovery_expense) AS RecoveryExpense,
   SUM(acq.purchase_apr) AS apr2,
   SUM(p.gross_revenue) AS GrossRevenue,
   SUM(p.net_revenue) AS NetRevenue,
   SUM(c.cash_inflow_amount) as CashInflow,
   SUM(c.cash_outflow_amount) as CashOutflow,
   SUM(c.net_cashflow) as NetCashFlow
FROM acq_agg acq
LEFT JOIN financials_agg f
   ON acq.credit_account_id = f.credit_account_id
LEFT JOIN bucket_agg b
   ON f.reporting_date = b.reporting_date
   AND f.month_on_book = b.months_on_book
   AND f.credit_account_id = b.credit_account_id
LEFT JOIN profit_agg p
  ON f.reporting_date = p.reporting_date
  AND f.month_on_book = p.month_on_book
  AND f.account_number_hk = p.account_number_hk
LEFT JOIN metrics_agg m
   ON p.reporting_date = m.reporting_date
   AND p.month_on_book = m.month_on_book
   AND p.account_number_hk = m.account_number_hk
LEFT JOIN reserve_agg r
   ON m.reporting_date = r.reporting_date
   AND m.month_on_book = r.month_on_book
   AND m.account_number_hk = r.account_number_hk
LEFT JOIN cashflow_agg c
   ON f.reporting_date = c.reporting_date
   AND f.account_number_hk = c.account_number_hk
LEFT JOIN fpd_acct fd
   ON f.credit_account_id = fd.credit_account_id
   AND f.month_on_book = fd.fpd_mob
GROUP BY Vintage, VintageDate, MonthsOnBooks, AccountNumber, Branding, Acquisitions, Association, AcqSource, Subchannel, AnnualFeeGroup, Fee, OriginalCreditLine, VantageRange
),

mapped AS (
    SELECT v.*, nm.segment AS rollup_segment, nm.fee_label AS rollup_fee
    FROM vcr v
    LEFT JOIN name_map nm
      ON  UPPER(TRIM(v.AcqSource)) = UPPER(TRIM(nm.src_acq_source))
      AND (nm.src_branding IS NULL OR UPPER(TRIM(v.Branding)) = UPPER(TRIM(nm.src_branding)))
      AND (nm.src_fee      IS NULL OR TRIM(v.Fee)             = TRIM(nm.src_fee))
),

-- every row twice: once under its product roll-up, once under its vantage band,
-- so the Vantage <=600 / 601-639 / 640+ rows get actuals as well
keyed AS (
    SELECT 'product' AS row_kind, rollup_segment AS segment, rollup_fee AS fee_label,
           'All' AS vantage_range, v.* EXCLUDE (rollup_segment, rollup_fee, VantageRange)
    FROM mapped v
    WHERE rollup_segment IS NOT NULL
    UNION ALL
    SELECT 'vantage', v.VantageRange, 'All', v.VantageRange,
           v.* EXCLUDE (rollup_segment, rollup_fee, VantageRange)
    FROM mapped v
    WHERE v.VantageRange IS NOT NULL
),

-- collapse Branding, OriginalCreditLine and every other breakdown
monthly AS (
    SELECT
        row_kind, segment, fee_label, vantage_range, Vintage, MonthsOnBooks,
        SUM(OriginalCreditLine * NewAccounts) AS line_x_boards,
        SUM(EndingReceivable) AS EndingReceivable,
        SUM(PrincipalReceivable) AS PrincipalReceivable,
        SUM(ActiveAccountIndicator) AS ActiveAccountIndicator,
        SUM(InactiveAccountIndicator) AS InactiveAccountIndicator,
        SUM(ActiveCreditLine) AS ActiveCreditLine,
        SUM(Bucket0Count) AS Bucket0Count,
        SUM(Bucket5Count) AS Bucket5Count,
        SUM(Bucket30Count) AS Bucket30Count,
        SUM(Bucket60Count) AS Bucket60Count,
        SUM(Bucket90Count) AS Bucket90Count,
        SUM(Bucket120Count) AS Bucket120Count,
        SUM(Bucket150Count) AS Bucket150Count,
        SUM(Bucket180Count) AS Bucket180Count,
        SUM(Bucket90PrincipalAmount) AS Bucket90PrincipalAmount,
        SUM(Bucket120PrincipalAmount) AS Bucket120PrincipalAmount,
        SUM(Bucket150PrincipalAmount) AS Bucket150PrincipalAmount,
        SUM(Bucket180PrincipalAmount) AS Bucket180PrincipalAmount,
        SUM(Bucket0Amount) AS Bucket0Amount,
        SUM(Bucket5Amount) AS Bucket5Amount,
        SUM(Bucket30Amount) AS Bucket30Amount,
        SUM(Bucket60Amount) AS Bucket60Amount,
        SUM(Bucket90Amount) AS Bucket90Amount,
        SUM(Bucket120Amount) AS Bucket120Amount,
        SUM(Bucket150Amount) AS Bucket150Amount,
        SUM(Bucket180Amount) AS Bucket180Amount,
        SUM(ACE2Score) AS ACE2Score,
        SUM(ACE4Score) AS ACE4Score,
        SUM(Vantage3score) AS Vantage3score,
        SUM(ACE2ScoreIndicator) AS ACE2ScoreIndicator,
        SUM(ACE4ScoreIndicator) AS ACE4ScoreIndicator,
        SUM(Vantage3ScoreIndicator) AS Vantage3ScoreIndicator,
        SUM(ReserveBalGrossAmount2) AS ReserveBalGrossAmount2,
        SUM(ReserveBalGrossAmount4) AS ReserveBalGrossAmount4,
        SUM(RequiredReserves) AS RequiredReserves,
        SUM(apr2) AS apr2,
        SUM(NewAccounts) AS NewAccounts,
        SUM(TotalFinanceCharges) AS TotalFinanceCharges,
        SUM(RewardsAmount) AS RewardsAmount,
        SUM(TotalNetSales) AS TotalNetSales,
        SUM(FeeAnnualChargeAmount) AS FeeAnnualChargeAmount,
        SUM(ChargeOffIndicator) AS ChargeOffIndicator,
        SUM(FraudCount) AS FraudCount,
        SUM(UnwindCount) AS UnwindCount,
        SUM(FraudLossAmount) AS FraudLossAmount,
        SUM(FraudAmount) AS FraudAmount,
        SUM(FraudNetAmount52) AS FraudNetAmount52,
        SUM(FraudGrossAmount88) AS FraudGrossAmount88,
        SUM(ChargeOffPrincipalAmount) AS ChargeOffPrincipalAmount,
        SUM(ChargeOffAmount) AS ChargeOffAmount,
        SUM(RecoveriesAmount) AS RecoveriesAmount,
        SUM(CreditProtectionAmount) AS CreditProtectionAmount,
        SUM(FeeLateAccruedAmount) AS FeeLateAccruedAmount,
        SUM(InterchangeRevenue) AS InterchangeRevenue,
        SUM(FeeDirectCheckAmount) AS FeeDirectCheckAmount,
        SUM(FeeCashAdvanceAmount) AS FeeCashAdvanceAmount,
        SUM(FeeCrLineIncreaseMiscAmt) AS FeeCrLineIncreaseMiscAmt,
        SUM(TotalFeeAdjustments) AS TotalFeeAdjustments,
        SUM(FeeMiscAccruedTtlAmt) AS FeeMiscAccruedTtlAmt,
        SUM(FeeEnrollmentAmount) AS FeeEnrollmentAmount,
        SUM(FeeOverlimitAmount) AS FeeOverlimitAmount,
        SUM(ProvisionExpense) AS ProvisionExpense,
        SUM(CollectionsExpense60Plus) AS CollectionsExpense60Plus,
        SUM(CollectionsExpensePreCalland530) AS CollectionsExpensePreCalland530,
        SUM(CostofFundsExpense) AS CostofFundsExpense,
        SUM(CreditProtectionExpense) AS CreditProtectionExpense,
        SUM(CustomerServiceExpense) AS CustomerServiceExpense,
        SUM(OneTimeBookingExpense) AS OneTimeBookingExpense,
        SUM(OtherOverheadExpense) AS OtherOverheadExpense,
        SUM(SystemsExpense) AS SystemsExpense,
        SUM(TotalNetPayments) AS TotalNetPayments,
        SUM(TotalCashAdvances) AS TotalCashAdvances,
        SUM(FeeCreditProtectionCount) AS FeeCreditProtectionCount,
        SUM(CreditLineIncreaseIndicator) AS CreditLineIncreaseIndicator,
        SUM(FeeCrLineIncreaseMiscCnt) AS FeeCrLineIncreaseMiscCnt,
        SUM(FreeCLI) AS FreeCLI,
        SUM(FeeDirectCheckCount) AS FeeDirectCheckCount,
        SUM(FeeLateAccruedCount) AS FeeLateAccruedCount,
        SUM(CurrentAccountLateFee) AS CurrentAccountLateFee,
        SUM(Attrition) AS Attrition,
        SUM(RetainedFlag) AS RetainedFlag,
        SUM(FeeAnnualDueMonthlyAmount) AS FeeAnnualDueMonthlyAmount,
        SUM(FeeAnnualMembershipAmount) AS FeeAnnualMembershipAmount,
        SUM(FeeDuplicateStatementAmount) AS FeeDuplicateStatementAmount,
        SUM(FeeFedExAmount) AS FeeFedExAmount,
        SUM(FeeFinanceChargeAmount) AS FeeFinanceChargeAmount,
        SUM(FeeLateAmount) AS FeeLateAmount,
        SUM(FeeReplacementAmount) AS FeeReplacementAmount,
        SUM(FeeReplacementManualAmount) AS FeeReplacementManualAmount,
        SUM(FeeSalesSlipAmount) AS FeeSalesSlipAmount,
        SUM(FeeOverlimitAdjustmentAmount) AS FeeOverlimitAdjustmentAmount,
        SUM(MiscFeeamount) AS MiscFeeamount,
        SUM(FPDCount) AS FPDCount,
        SUM(FPDEval) AS FPDEval,
        SUM(RecoveryExpense) AS RecoveryExpense,
        SUM(GrossRevenue) AS GrossRevenue,
        SUM(NetRevenue) AS NetRevenue,
        SUM(CashInflow) AS CashInflow,
        SUM(CashOutflow) AS CashOutflow,
        SUM(NetCashFlow) AS NetCashFlow,
        COUNT(*) AS source_rows
    FROM keyed
    GROUP BY row_kind, segment, fee_label, vantage_range, Vintage, MonthsOnBooks
),

-- flows add up from MOB 1; stocks stay as at this MOB
cumulative AS (
    SELECT
        m.row_kind, m.segment, m.fee_label, m.vantage_range, m.Vintage,
        m.MonthsOnBooks,
        m.EndingReceivable,
        m.PrincipalReceivable,
        m.ActiveAccountIndicator,
        m.InactiveAccountIndicator,
        m.ActiveCreditLine,
        m.Bucket0Count,
        m.Bucket5Count,
        m.Bucket30Count,
        m.Bucket60Count,
        m.Bucket90Count,
        m.Bucket120Count,
        m.Bucket150Count,
        m.Bucket180Count,
        m.Bucket90PrincipalAmount,
        m.Bucket120PrincipalAmount,
        m.Bucket150PrincipalAmount,
        m.Bucket180PrincipalAmount,
        m.Bucket0Amount,
        m.Bucket5Amount,
        m.Bucket30Amount,
        m.Bucket60Amount,
        m.Bucket90Amount,
        m.Bucket120Amount,
        m.Bucket150Amount,
        m.Bucket180Amount,
        m.ACE2Score,
        m.ACE4Score,
        m.Vantage3score,
        m.ACE2ScoreIndicator,
        m.ACE4ScoreIndicator,
        m.Vantage3ScoreIndicator,
        m.ReserveBalGrossAmount2,
        m.ReserveBalGrossAmount4,
        m.RequiredReserves,
        m.apr2,
        SUM(m.NewAccounts) OVER w AS NewAccounts,
        SUM(m.TotalFinanceCharges) OVER w AS TotalFinanceCharges,
        SUM(m.RewardsAmount) OVER w AS RewardsAmount,
        SUM(m.TotalNetSales) OVER w AS TotalNetSales,
        SUM(m.FeeAnnualChargeAmount) OVER w AS FeeAnnualChargeAmount,
        SUM(m.ChargeOffIndicator) OVER w AS ChargeOffIndicator,
        SUM(m.FraudCount) OVER w AS FraudCount,
        SUM(m.UnwindCount) OVER w AS UnwindCount,
        SUM(m.FraudLossAmount) OVER w AS FraudLossAmount,
        SUM(m.FraudAmount) OVER w AS FraudAmount,
        SUM(m.FraudNetAmount52) OVER w AS FraudNetAmount52,
        SUM(m.FraudGrossAmount88) OVER w AS FraudGrossAmount88,
        SUM(m.ChargeOffPrincipalAmount) OVER w AS ChargeOffPrincipalAmount,
        SUM(m.ChargeOffAmount) OVER w AS ChargeOffAmount,
        SUM(m.RecoveriesAmount) OVER w AS RecoveriesAmount,
        SUM(m.CreditProtectionAmount) OVER w AS CreditProtectionAmount,
        SUM(m.FeeLateAccruedAmount) OVER w AS FeeLateAccruedAmount,
        SUM(m.InterchangeRevenue) OVER w AS InterchangeRevenue,
        SUM(m.FeeDirectCheckAmount) OVER w AS FeeDirectCheckAmount,
        SUM(m.FeeCashAdvanceAmount) OVER w AS FeeCashAdvanceAmount,
        SUM(m.FeeCrLineIncreaseMiscAmt) OVER w AS FeeCrLineIncreaseMiscAmt,
        SUM(m.TotalFeeAdjustments) OVER w AS TotalFeeAdjustments,
        SUM(m.FeeMiscAccruedTtlAmt) OVER w AS FeeMiscAccruedTtlAmt,
        SUM(m.FeeEnrollmentAmount) OVER w AS FeeEnrollmentAmount,
        SUM(m.FeeOverlimitAmount) OVER w AS FeeOverlimitAmount,
        SUM(m.ProvisionExpense) OVER w AS ProvisionExpense,
        SUM(m.CollectionsExpense60Plus) OVER w AS CollectionsExpense60Plus,
        SUM(m.CollectionsExpensePreCalland530) OVER w AS CollectionsExpensePreCalland530,
        SUM(m.CostofFundsExpense) OVER w AS CostofFundsExpense,
        SUM(m.CreditProtectionExpense) OVER w AS CreditProtectionExpense,
        SUM(m.CustomerServiceExpense) OVER w AS CustomerServiceExpense,
        SUM(m.OneTimeBookingExpense) OVER w AS OneTimeBookingExpense,
        SUM(m.OtherOverheadExpense) OVER w AS OtherOverheadExpense,
        SUM(m.SystemsExpense) OVER w AS SystemsExpense,
        SUM(m.TotalNetPayments) OVER w AS TotalNetPayments,
        SUM(m.TotalCashAdvances) OVER w AS TotalCashAdvances,
        SUM(m.FeeCreditProtectionCount) OVER w AS FeeCreditProtectionCount,
        SUM(m.CreditLineIncreaseIndicator) OVER w AS CreditLineIncreaseIndicator,
        SUM(m.FeeCrLineIncreaseMiscCnt) OVER w AS FeeCrLineIncreaseMiscCnt,
        SUM(m.FreeCLI) OVER w AS FreeCLI,
        SUM(m.FeeDirectCheckCount) OVER w AS FeeDirectCheckCount,
        SUM(m.FeeLateAccruedCount) OVER w AS FeeLateAccruedCount,
        SUM(m.CurrentAccountLateFee) OVER w AS CurrentAccountLateFee,
        SUM(m.Attrition) OVER w AS Attrition,
        SUM(m.RetainedFlag) OVER w AS RetainedFlag,
        SUM(m.FeeAnnualDueMonthlyAmount) OVER w AS FeeAnnualDueMonthlyAmount,
        SUM(m.FeeAnnualMembershipAmount) OVER w AS FeeAnnualMembershipAmount,
        SUM(m.FeeDuplicateStatementAmount) OVER w AS FeeDuplicateStatementAmount,
        SUM(m.FeeFedExAmount) OVER w AS FeeFedExAmount,
        SUM(m.FeeFinanceChargeAmount) OVER w AS FeeFinanceChargeAmount,
        SUM(m.FeeLateAmount) OVER w AS FeeLateAmount,
        SUM(m.FeeReplacementAmount) OVER w AS FeeReplacementAmount,
        SUM(m.FeeReplacementManualAmount) OVER w AS FeeReplacementManualAmount,
        SUM(m.FeeSalesSlipAmount) OVER w AS FeeSalesSlipAmount,
        SUM(m.FeeOverlimitAdjustmentAmount) OVER w AS FeeOverlimitAdjustmentAmount,
        SUM(m.MiscFeeamount) OVER w AS MiscFeeamount,
        SUM(m.FPDCount) OVER w AS FPDCount,
        SUM(m.FPDEval) OVER w AS FPDEval,
        SUM(m.RecoveryExpense) OVER w AS RecoveryExpense,
        SUM(m.GrossRevenue) OVER w AS GrossRevenue,
        SUM(m.NetRevenue) OVER w AS NetRevenue,
        SUM(m.CashInflow) OVER w AS CashInflow,
        SUM(m.CashOutflow) OVER w AS CashOutflow,
        SUM(m.NetCashFlow) OVER w AS NetCashFlow,
        SUM(m.line_x_boards) OVER w        AS cum_line_x_boards,
        AVG(m.EndingReceivable) OVER w     AS avg_receivable_to_date
    FROM monthly m
    WINDOW w AS (PARTITION BY m.row_kind, m.segment, m.fee_label, m.Vintage
                 ORDER BY m.MonthsOnBooks
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),

-- ---------------------------------------------------------------------------
-- CONFIRM THESE THREE. Everything above is arithmetic on the BAU query's own
-- columns; these are definitions, and the BAU query leaves pre-tax income to
-- "existing calculation upstream in VCR", so check them against that before you
-- trust the ROA and PTI columns. The components are all in the output, so a
-- correction here changes one expression and nothing else.
-- ---------------------------------------------------------------------------
rates AS (
    SELECT c.*,
        c.GrossRevenue
          - c.ProvisionExpense          - c.FraudLossAmount
          - c.CollectionsExpense60Plus  - c.CollectionsExpensePreCalland530
          - c.CostofFundsExpense        - c.CreditProtectionExpense
          - c.CustomerServiceExpense    - c.OneTimeBookingExpense
          - c.OtherOverheadExpense      - c.SystemsExpense
          - c.RecoveryExpense           - c.RewardsAmount   AS cum_pre_tax_income
    FROM cumulative c
)

SELECT
    LEFT(r.Vintage::VARCHAR, 7)                     AS "Vintage",
    r.segment                                       AS "segment",
    'All'                                           AS "Branding",
    r.fee_label                                     AS "Fee",
    'All'                                           AS "OriginalCreditLine",
    r.MonthsOnBooks                                 AS "mob",

    -- what the heat map reads
    r.NewAccounts                                   AS "Boards",
    r.cum_line_x_boards / NULLIF(r.NewAccounts, 0)  AS "Avg_InitialLinePerBooked",
    r.ChargeOffIndicator / NULLIF(r.NewAccounts, 0) AS "CumUnitRate",
    (r.ChargeOffPrincipalAmount - r.RecoveriesAmount)
        / NULLIF(r.avg_receivable_to_date, 0)       AS "CumNetDollar",
    r.cum_pre_tax_income
        / NULLIF(r.avg_receivable_to_date, 0)
        * (12.0 / NULLIF(r.MonthsOnBooks, 0))       AS "CumulativeROA",
    r.cum_pre_tax_income / NULLIF(r.NewAccounts, 0) AS "CumPTI",
    r.ActiveAccountIndicator                        AS "TotalActives",
    r.EndingReceivable                              AS "EndingReceivables",
    r.cum_pre_tax_income / NULLIF(r.NewAccounts, 0) AS "CumlProfitPerBooked",
    r.GrossRevenue / NULLIF(r.NewAccounts, 0)       AS "CumlGrossRevPerBooked",
    r.Bucket30Count / NULLIF(r.ActiveAccountIndicator, 0)  AS "ThirtyPlusUnit",
    r.Bucket30Amount / NULLIF(r.EndingReceivable, 0)       AS "ThirtyPlusDoll",
    r.Bucket60Count / NULLIF(r.ActiveAccountIndicator, 0)  AS "SixtyPlusUnit",
    r.Bucket60Amount / NULLIF(r.EndingReceivable, 0)       AS "SixtyPlusDoll",
    r.EndingReceivable / NULLIF(r.ActiveAccountIndicator, 0) AS "Avg_BalancePerActive",

    -- every attribute and measure the BAU query produces, kept
    r.row_kind                                      AS "RowKind",
    r.vantage_range                                 AS "VantageRange",
    r.cum_pre_tax_income                            AS "CumPreTaxIncome",
    r.avg_receivable_to_date                        AS "AvgReceivableToDate",
    r.EndingReceivable AS "EndingReceivable",
    r.PrincipalReceivable AS "PrincipalReceivable",
    r.ActiveAccountIndicator AS "ActiveAccountIndicator",
    r.InactiveAccountIndicator AS "InactiveAccountIndicator",
    r.ActiveCreditLine AS "ActiveCreditLine",
    r.Bucket0Count AS "Bucket0Count",
    r.Bucket5Count AS "Bucket5Count",
    r.Bucket30Count AS "Bucket30Count",
    r.Bucket60Count AS "Bucket60Count",
    r.Bucket90Count AS "Bucket90Count",
    r.Bucket120Count AS "Bucket120Count",
    r.Bucket150Count AS "Bucket150Count",
    r.Bucket180Count AS "Bucket180Count",
    r.Bucket90PrincipalAmount AS "Bucket90PrincipalAmount",
    r.Bucket120PrincipalAmount AS "Bucket120PrincipalAmount",
    r.Bucket150PrincipalAmount AS "Bucket150PrincipalAmount",
    r.Bucket180PrincipalAmount AS "Bucket180PrincipalAmount",
    r.Bucket0Amount AS "Bucket0Amount",
    r.Bucket5Amount AS "Bucket5Amount",
    r.Bucket30Amount AS "Bucket30Amount",
    r.Bucket60Amount AS "Bucket60Amount",
    r.Bucket90Amount AS "Bucket90Amount",
    r.Bucket120Amount AS "Bucket120Amount",
    r.Bucket150Amount AS "Bucket150Amount",
    r.Bucket180Amount AS "Bucket180Amount",
    r.ACE2Score AS "ACE2Score",
    r.ACE4Score AS "ACE4Score",
    r.Vantage3score AS "Vantage3score",
    r.ACE2ScoreIndicator AS "ACE2ScoreIndicator",
    r.ACE4ScoreIndicator AS "ACE4ScoreIndicator",
    r.Vantage3ScoreIndicator AS "Vantage3ScoreIndicator",
    r.ReserveBalGrossAmount2 AS "ReserveBalGrossAmount2",
    r.ReserveBalGrossAmount4 AS "ReserveBalGrossAmount4",
    r.RequiredReserves AS "RequiredReserves",
    r.apr2 AS "apr2",
    r.NewAccounts AS "NewAccounts",
    r.TotalFinanceCharges AS "TotalFinanceCharges",
    r.RewardsAmount AS "RewardsAmount",
    r.TotalNetSales AS "TotalNetSales",
    r.FeeAnnualChargeAmount AS "FeeAnnualChargeAmount",
    r.ChargeOffIndicator AS "ChargeOffIndicator",
    r.FraudCount AS "FraudCount",
    r.UnwindCount AS "UnwindCount",
    r.FraudLossAmount AS "FraudLossAmount",
    r.FraudAmount AS "FraudAmount",
    r.FraudNetAmount52 AS "FraudNetAmount52",
    r.FraudGrossAmount88 AS "FraudGrossAmount88",
    r.ChargeOffPrincipalAmount AS "ChargeOffPrincipalAmount",
    r.ChargeOffAmount AS "ChargeOffAmount",
    r.RecoveriesAmount AS "RecoveriesAmount",
    r.CreditProtectionAmount AS "CreditProtectionAmount",
    r.FeeLateAccruedAmount AS "FeeLateAccruedAmount",
    r.InterchangeRevenue AS "InterchangeRevenue",
    r.FeeDirectCheckAmount AS "FeeDirectCheckAmount",
    r.FeeCashAdvanceAmount AS "FeeCashAdvanceAmount",
    r.FeeCrLineIncreaseMiscAmt AS "FeeCrLineIncreaseMiscAmt",
    r.TotalFeeAdjustments AS "TotalFeeAdjustments",
    r.FeeMiscAccruedTtlAmt AS "FeeMiscAccruedTtlAmt",
    r.FeeEnrollmentAmount AS "FeeEnrollmentAmount",
    r.FeeOverlimitAmount AS "FeeOverlimitAmount",
    r.ProvisionExpense AS "ProvisionExpense",
    r.CollectionsExpense60Plus AS "CollectionsExpense60Plus",
    r.CollectionsExpensePreCalland530 AS "CollectionsExpensePreCalland530",
    r.CostofFundsExpense AS "CostofFundsExpense",
    r.CreditProtectionExpense AS "CreditProtectionExpense",
    r.CustomerServiceExpense AS "CustomerServiceExpense",
    r.OneTimeBookingExpense AS "OneTimeBookingExpense",
    r.OtherOverheadExpense AS "OtherOverheadExpense",
    r.SystemsExpense AS "SystemsExpense",
    r.TotalNetPayments AS "TotalNetPayments",
    r.TotalCashAdvances AS "TotalCashAdvances",
    r.FeeCreditProtectionCount AS "FeeCreditProtectionCount",
    r.CreditLineIncreaseIndicator AS "CreditLineIncreaseIndicator",
    r.FeeCrLineIncreaseMiscCnt AS "FeeCrLineIncreaseMiscCnt",
    r.FreeCLI AS "FreeCLI",
    r.FeeDirectCheckCount AS "FeeDirectCheckCount",
    r.FeeLateAccruedCount AS "FeeLateAccruedCount",
    r.CurrentAccountLateFee AS "CurrentAccountLateFee",
    r.Attrition AS "Attrition",
    r.RetainedFlag AS "RetainedFlag",
    r.FeeAnnualDueMonthlyAmount AS "FeeAnnualDueMonthlyAmount",
    r.FeeAnnualMembershipAmount AS "FeeAnnualMembershipAmount",
    r.FeeDuplicateStatementAmount AS "FeeDuplicateStatementAmount",
    r.FeeFedExAmount AS "FeeFedExAmount",
    r.FeeFinanceChargeAmount AS "FeeFinanceChargeAmount",
    r.FeeLateAmount AS "FeeLateAmount",
    r.FeeReplacementAmount AS "FeeReplacementAmount",
    r.FeeReplacementManualAmount AS "FeeReplacementManualAmount",
    r.FeeSalesSlipAmount AS "FeeSalesSlipAmount",
    r.FeeOverlimitAdjustmentAmount AS "FeeOverlimitAdjustmentAmount",
    r.MiscFeeamount AS "MiscFeeamount",
    r.FPDCount AS "FPDCount",
    r.FPDEval AS "FPDEval",
    r.RecoveryExpense AS "RecoveryExpense",
    r.GrossRevenue AS "GrossRevenue",
    r.NetRevenue AS "NetRevenue",
    r.CashInflow AS "CashInflow",
    r.CashOutflow AS "CashOutflow",
    r.NetCashFlow AS "NetCashFlow",
    r.MonthsOnBooks                                 AS "MonthsOnBooks"
FROM rates r
WHERE r.MonthsOnBooks IN (12, 24, 36)
ORDER BY r.row_kind, r.segment, r.fee_label, r.MonthsOnBooks, "Vintage";
