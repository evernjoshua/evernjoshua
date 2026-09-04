libname unixcurr '/sasdata/unix/Risk_Financial/Acquisitions_Finance/Boards/'      access=readonly;
libname unixhist '/sasdata/unix/Risk_Financial/Acquisitions_Finance/Historicals/' access=readonly;

proc contents data=unixhist.boards3;
run;

/*---------------------------------------------------------------
Step1: base pull, filtered up front.
creditaccountid is kept so the BureauScore join can happen.
AccountNumber is built from FirstSecond. The WHERE keeps only
'FA', so 'Multiple Account' should never appear - the ELSE is
there so a future data change shows up as a value instead of
silently mislabelling rows as First Account.
---------------------------------------------------------------*/
DATA Step1;
  LENGTH AccountNumber $16;
  SET unixhist.boards3 (WHERE=(Openmonthend ge '01Jan2023'd
                           and FirstSecond = 'FA'
                           and Subchannel  = 'PQ'
                           and Branding   ne 'Secured')
          KEEP=creditaccountid
          vintage ReportingDate FirstSecond Branding Acquisitions
          Association   Source Subchannel Annual_Fee initialline
          NewAccountIndicator FeeAnnualChargeAmount TotalFinanceCharges EndingReceivable TotalNetSales
          ACE2Score ACE2ScoreIndicator ActiveAccountIndicator FraudCount CurrentMonthUnwindIndicator ChargeOffIndicator
          PrincipalReceivable InactiveAccountIndicator FraudGrossAmount88 FraudNetAmount52
          ChargeOffPrincipalAmount ChargeOffAmount FeeAnnualChargeAmount TotalFinanceCharges
          FeeLateAccruedAmount FeeDirectCheckAmount FeeCashAdvanceAmount
          TotalFeeAdjustments creditlineactive FeeMiscAccruedTtlAmt FeeEnrollmentAmount FeeOverlimitAmount TotalMiscellaneous
          ReserveBalGrossAmount2 FeeCreditLineIncreaseMiscellaneo
          TotalPaymentAdjustments TotalCashAdvances FeeCreditProtectionAmount rewardsamount fraudamount VantageScoreCount

          FeeLateCount Vantagescore FeeCreditProtectionCount CreditLineIncreaseIndicator FeeCRLineIncreaseMiscCnt FeeDirectCheckCount FeeLateCount
          FeeLateAccruedCount
          FreeCLI Attrition OpeningReceivable CurrentAccountLateFee ACE4Score ACE4ScoreIndicator ReserveBalanceGrossAmount4
          TotalCurrentBucketAmount TotalCurrentBucketCount
          Bucket5Amount Bucket5Count
          Bucket30Amount Bucket30Count
          Bucket60Amount Bucket60Count
          Bucket90Amount Bucket90Count Bucket90PrinAmount
          Bucket120Amount Bucket120Count Bucket120PrinAmount
          Bucket150Amount Bucket150Count Bucket150PrinAmount
          Bucket180Amount Bucket180Count

          TotalRPCPayments TotalDirectWU
          RetainedFlag
          FeeAnnualDueMonthlyAmount FeeAnnualMembershipAmount FeeDuplicateStatementAmount FeeFedExAmount FeeFinanceChargeAmount FeeLateAmount FeeReplacementAmount FeeReplacementManualAmount FeeSalesSlipAmount FeeOverlimitAdjustmentAmount MiscFeeamount
          CreditLifeAdjustmentAmount CreditLifeChargebackAmount
          ScorexPlusScore ScorexPlusCount
          thirtyplus thirtypluscount fpd
          apr2
          Openmonthend
);
AnnualFeeGroup=Annual_Fee;

IF FirstSecond = 'FA' THEN AccountNumber = 'First Account';
ELSE                       AccountNumber = 'Multiple Account';

OriginalCreditLine=initialline;
UnwindIndicator=CurrentMonthUnwindIndicator;
ActiveCreditLine=creditlineactive;
FeeCrLineIncreaseMiscAmt=FeeCreditLineIncreaseMiscellaneo;
CreditProtectionAmount=FeeCreditProtectionAmount;
FraudLossAmount=fraudamount;
Vantage3Score=VantageScore;
Vantage3ScoreIndicator=VantageScoreCount;
ReserveBalGrossAmount4=ReserveBalanceGrossAmount4;
RUN;

/* Sanity check that the FA filter really did leave one bucket. */
PROC FREQ DATA=Step1;
TABLES FirstSecond * AccountNumber / LIST MISSING;
RUN;

/*---------------------------------------------------------------
Row-count check: if boards2_all has more than one row per
creditaccountid the join will fan out and inflate every SUM.
Run this before trusting the output.
---------------------------------------------------------------*/
PROC SQL;
SELECT count(*) as Rows, count(distinct creditaccountid) as DistinctAccts
FROM unixcurr.boards2_all;
QUIT;

/*---------------------------------------------------------------
Step1a: attach BureauScore
---------------------------------------------------------------*/
PROC SQL;
CREATE TABLE Step1a AS
SELECT
    a.*
  , b.c1b_source_id
  , b.c1b_descriptor_id
  , b.BureauScore
FROM Step1 a
LEFT JOIN unixcurr.boards2_all b
  ON a.creditaccountid = b.creditaccountid
;
QUIT;

/*---------------------------------------------------------------
Step1b: band the score into VantageRange.
LENGTH first so the band text is not truncated.
Missing scores are called out rather than falling into '<=600'.
---------------------------------------------------------------*/
DATA Step1b (drop=creditaccountid c1b_source_id c1b_descriptor_id BureauScore);
  LENGTH VantageRange $15;
  SET Step1a;

       IF missing(BureauScore)       THEN VantageRange = 'Unknown';
  ELSE IF BureauScore le 600         THEN VantageRange = '<=600';
  ELSE IF 601 le BureauScore le 639  THEN VantageRange = '601-639';
  ELSE                                    VantageRange = '640+';
RUN;

/*---------------------------------------------------------------
Step2: aggregate
---------------------------------------------------------------*/
PROC SQL;
CREATE TABLE Step2 AS
SELECT
    Vintage
  , intnx('month',mdy(input(substr(Vintage,1,index(Vintage,'-')-1), 2.),1,input(substr(Vintage,index(Vintage,'-')+1,4), 4.)),0,'end') as VintageDate format date9.
  , intck('month',calculated VintageDate, ReportingDate) +1 as MonthsOnBooks

  , AccountNumber   /* from FirstSecond */
  , VantageRange    /* banded BureauScore */

  , Branding
  , CASE
    WHEN Acquisitions = 'PQ-NT'     THEN 'Prequal - Non-Targeted'
    WHEN Acquisitions = 'PQ-CTG'    THEN 'Prequal - Credit-Targeted'
    WHEN Acquisitions = 'PQ-OB ITA' THEN 'Prequal - Outbound ITA'
    ELSE 'Other' END as Acquisitions

  , Association
  , Source
  , CASE
    WHEN Subchannel = 'PQ' THEN 'Prequal'
    ELSE 'Other' END as Subchannel

  , AnnualFeeGroup
  , CASE WHEN index(AnnualFeeGroup,'/') > 2
         THEN substr(AnnualFeeGroup,1,index(AnnualFeeGroup,'/')-2)
         ELSE AnnualFeeGroup END as Fee
  , OriginalCreditLine

  , SUM(NewAccountIndicator) as NewAccounts
  , SUM(TotalFinanceCharges) as TotalFinanceCharges
  , SUM(EndingReceivable) as EndingReceivable
  , SUM(RewardsAmount) as RewardsAmount
  , SUM(TotalNetSales) as TotalNetSales

  , SUM(FeeAnnualChargeAmount) as FeeAnnualChargeAmount

  , SUM(TotalCurrentBucketCount) as Bucket0Count
  , SUM(Bucket5Count) as Bucket5Count
  , SUM(Bucket30Count) as Bucket30Count
  , SUM(Bucket60Count) as Bucket60Count
  , SUM(Bucket90Count) as Bucket90Count
  , SUM(Bucket120Count) as Bucket120Count
  , SUM(Bucket150Count) as Bucket150Count
  , SUM(Bucket180Count) as Bucket180Count

  , SUM(TotalCurrentBucketAmount) as Bucket0Amount
  , SUM(Bucket5Amount) as Bucket5Amount
  , SUM(Bucket30Amount) as Bucket30Amount
  , SUM(Bucket60Amount) as Bucket60Amount
  , SUM(Bucket90Amount) as Bucket90Amount
  , SUM(Bucket120Amount) as Bucket120Amount
  , SUM(Bucket150Amount) as Bucket150Amount
  , SUM(Bucket180Amount) as Bucket180Amount

  , SUM(Bucket90PrinAmount) as Bucket90PrincipalAmount
  , SUM(Bucket120PrinAmount) as Bucket120PrincipalAmount
  , SUM(Bucket150PrinAmount) as Bucket150PrincipalAmount

  , SUM(ChargeOffIndicator) as ChargeOffIndicator
  , SUM(FraudCount) as FraudCount
  , SUM(UnwindIndicator) as UnwindCount

  , SUM(ACE2Score) as ACE2Score
  , SUM(ACE4Score) as ACE4Score
  , SUM(Vantage3score) as Vantage3score
  , SUM(ACE2ScoreIndicator) as ACE2ScoreIndicator
  , SUM(ACE4ScoreIndicator) as ACE4ScoreIndicator
  , SUM(ActiveAccountIndicator) as ActiveAccountIndicator
  , SUM(InactiveAccountIndicator) as InactiveAccountIndicator
  , SUM(PrincipalReceivable) as PrincipalReceivable
  , SUM(FraudLossAmount) as FraudLossAmount
  , SUM(FraudNetAmount52) as FraudNetAmount52
  , SUM(FraudGrossAmount88) as FraudGrossAmount88

  , SUM(ChargeOffPrincipalAmount) as ChargeOffPrincipalAmount
  , SUM(ChargeOffAmount) as ChargeOffAmount
  , SUM(CreditProtectionAmount) as CreditProtectionAmount

  , SUM(FeeLateAccruedAmount) as FeeLateAccruedAmount
  , SUM(FeeDirectCheckAmount) as FeeDirectCheckAmount
  , SUM(FeeCashAdvanceAmount) as FeeCashAdvanceAmount
  , SUM(FeeCrLineIncreaseMiscAmt) as FeeCrLineIncreaseMiscAmt

  , SUM(TotalFeeAdjustments) as TotalFeeAdjustments

  , SUM(ActiveCreditLine ) as ActiveCreditLine
  , SUM(FeeMiscAccruedTtlAmt ) as FeeMiscAccruedTtlAmt
  , SUM(FeeEnrollmentAmount ) as FeeEnrollmentAmount
  , SUM(FeeOverlimitAmount ) as FeeOverlimitAmount
  , SUM(TotalMiscellaneous) as TotalMiscellaneous
  , SUM(ReserveBalGrossAmount2 ) as ReserveBalGrossAmount2
  , SUM(ReserveBalGrossAmount4 ) as ReserveBalGrossAmount4

  , SUM(TotalPaymentAdjustments) as TotalPaymentAdjustments

  , SUM(Vantage3ScoreIndicator) as Vantage3ScoreIndicator
  , SUM(TotalCashAdvances) as TotalCashAdvances
  , SUM(FeeCreditProtectionCount) as FeeCreditProtectionCount
  , SUM(CreditLineIncreaseIndicator) as CreditLineIncreaseIndicator
  , SUM(FeeCrLineIncreaseMiscCnt) as FeeCrLineIncreaseMiscCnt
  , SUM(FeeDirectCheckCount) as FeeDirectCheckCount
  , SUM(FeeLateCount) as FeeLateCount
  , SUM(CurrentAccountLateFee) as CurrentAccountLateFee
  , SUM(FeeLateAccruedCount) as FeeLateAccruedCount
  , SUM(FreeCLI) as FreeCLI
  , SUM(Attrition) as Attrition
  , SUM(OpeningReceivable) as OpeningReceivable

  , SUM(TotalRPCPayments) as TotalRPCPayments
  , SUM(TotalDirectWU) as TotalDirectWU

  , SUM(RetainedFlag) as RetainedFlag

  , SUM(FeeAnnualDueMonthlyAmount) as FeeAnnualDueMonthlyAmount
  , SUM(FeeAnnualMembershipAmount) as FeeAnnualMembershipAmount
  , SUM(FeeDuplicateStatementAmount) as FeeDuplicateStatementAmount
  , SUM(FeeFedExAmount) as FeeFedExAmount
  , SUM(FeeFinanceChargeAmount) as FeeFinanceChargeAmount
  , SUM(FeeLateAmount) as FeeLateAmount
  , SUM(FeeReplacementAmount) as FeeReplacementAmount
  , SUM(FeeReplacementManualAmount) as FeeReplacementManualAmount
  , SUM(FeeSalesSlipAmount) as FeeSalesSlipAmount
  , SUM(FeeOverlimitAdjustmentAmount) as FeeOverlimitAdjustmentAmount
  , SUM(MiscFeeamount) as MiscFeeamount

  , SUM(CreditLifeAdjustmentAmount) as CreditLifeAdjustmentAmount
  , SUM(CreditLifeChargebackAmount) as CreditLifeChargebackAmount

  , SUM(ScorexPlusScore) as ScorexPlusScore
  , SUM(ScorexPlusCount) as ScorexPlusCount

  , SUM(thirtyplus) as thirtyplus
  , SUM(thirtypluscount) as thirtypluscount
  , SUM(fpd) as fpd
  , SUM(apr2) as apr2

FROM Step1b
GROUP BY
    Vintage
  , calculated VintageDate
  , calculated MonthsOnBooks
  , AccountNumber
  , VantageRange
  , Branding
  , calculated Acquisitions
  , Association
  , Source
  , calculated Subchannel
  , AnnualFeeGroup
  , calculated Fee
  , OriginalCreditLine
;
QUIT;

proc export data= Step2
outfile='/sasdata/windows/fnbmcorp/Risk/Portfolio Growth/Personal Folders/Evern Joshua/VCRData_CG.csv'
dbms= CSV replace;
run;
