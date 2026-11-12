SET reporting_start_date = '2026-01-01';
SET reporting_end_date = '2026-09-30';
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
)
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
ORDER BY Vintage, VintageDate, MonthsOnBooks, AccountNumber, Branding, Acquisitions, Association, AcqSource, Subchannel, AnnualFeeGroup, Fee, OriginalCreditLine, VantageRange
;
