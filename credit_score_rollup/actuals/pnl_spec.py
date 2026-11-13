"""The P&L lines, transcribed from the spec document.

Nothing here is inferred: each line names the CSV column it reads. Where the
document gives a formula instead of a column it is marked DERIVED, and where it
asks for something the CSV does not carry it is marked MISSING and reads zero
until you point it at a source.
"""

# ---------------------------------------------------------------- revenues --
# sign +1 adds to gross revenue, -1 is a contra shown in brackets in the doc
REVENUE_LINES = [
    ("Enrollment Fees",        "FeeEnrollmentAmount",      +1),
    ("Credit Protection Fees", "CreditProtectionAmount",   +1),
    ("Annual Fees",            "FeeAnnualChargeAmount",    +1),
    ("Finance Charges",        "TotalFinanceCharges",      +1),
    ("Late Fees",              "FeeLateAccruedAmount",     +1),
    ("Overlimit Fees",         "FeeOverlimitAmount",       +1),
    ("NSF Fees",               "FeeMiscAccruedTtlAmt",     +1),
    ("Interchange Income",     "InterchangeRevenue",       +1),
    ("Direct Check Fees",      "FeeDirectCheckAmount",     +1),
    ("Cash Advance Fees",      "FeeCashAdvanceAmount",     +1),
    ("CLI Fees",               "FeeCrLineIncreaseMiscAmt", +1),
    ("(Rewards)",              "RewardsAmount",            -1),
    ("(Fee Reversals)",        "TotalFeeAdjustments",      -1),
]
# DERIVED: "Gross Revenue - sum(all other revenues except net revenue)", so the
# named lines plus this one always add back to GrossRevenue exactly.
MISC_REVENUE_LINE = "Miscellaneous Fees/Income"

GROSS_REVENUE   = "GrossRevenue"        # Total Gross Revenues
PROVISION       = "ProvisionExpense"    # (Provision for Loan Loss)
# Total Net Revenues = Gross Revenue + (Provision Expense). The brackets make it
# a deduction, so net = gross - provision when provision is carried positive.
# Set to -1 if your CSV already carries provision as a negative number.
PROVISION_SIGN = -1

# ---------------------------------------------------------------- expenses --
SERVICING_EXPENSE_LINES = [
    ("Customer Service",             "CustomerServiceExpense"),
    ("Collections (Pre-Call, 5-30)", "CollectionsExpensePreCalland530"),
    ("Collections (60+)",            "CollectionsExpense60Plus"),
    ("Systems",                      "SystemsExpense"),
    ("Credit Protection Expense",    "CreditProtectionExpense"),
    ("Other Overhead",               "OtherOverheadExpense"),
]

OTHER_EXPENSE_LINES = [
    ("Cost of Funds - Debt Expense", "CostofFundsExpense"),
    ("One Time - Booking Expense",   "OneTimeBookingExpense"),
    ("Recovery Expense",             "RecoveryExpense"),
]
# DERIVED: Fraud Loss Expense = FraudGrossAmount88 + FraudNetAmount52
FRAUD_LOSS_PARTS = ["FraudGrossAmount88", "FraudNetAmount52"]

# MISSING: the CSV has no CPA column. Point CPA_COLUMN at one if it gains
# a marketing cost, or leave it None and the line reads zero.
CPA_COLUMN = None

# MISSING: "Amex Incentive Expense - if date >= feb 2024 and mob <= 24, then
# 2.03 * amex_share * booked accounts / 24, and negate it". amex_share is not in
# the CSV. Fill in AMEX_SHARE to switch the line on.
AMEX_INCENTIVE = dict(
    rate=2.03,
    share=None,                  # <- the amex_share the document means
    from_vintage="2024-02",      # date >= feb 2024
    max_mob=24,                  # and mob <= 24
    months=24,                   # the /24
)

# ------------------------------------------------------------------- rates --
# Cumulative net charge-off before recoveries
#     = ChargeOffPrincipalAmount / Avg Total Gross Receivables - End of Period
# Cumulative ROA - Annualized
#     = (Cumul. Pre-Tax Income / Avg Gross Receivables - EOP) / MOB * 12
# Cumulative Unit Charge-Off Rate
#     = ChargeOffIndicator / active accounts
# The other reading of the document's line is booked accounts less unwinds
# through MOB 4; keep it available with unit_co_denominator="boards_net_unwind".
UNIT_CO_DENOMINATOR = "active"
UNWIND_THROUGH_MOB = 4
RECEIVABLE_COLUMN  = "EndingReceivable"
BOARDS_COLUMN      = "NewAccounts"
UNWIND_COLUMN      = "UnwindCount"
CHARGE_OFF_UNITS   = "ChargeOffIndicator"
CHARGE_OFF_PRIN    = "ChargeOffPrincipalAmount"
ACTIVE_COLUMN      = "ActiveAccountIndicator"
