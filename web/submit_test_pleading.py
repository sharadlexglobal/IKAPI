"""Submit the Bhandari vs Canara Bank pleading to the pipeline for testing."""
import json
import requests
import sys
import os

PLEADING_TEXT = """IN THE HIGH COURT OF JUDICATURE FOR RAJASTHAN AT JAIPUR
(ORDINARY ORIGINAL CIVIL JURISDICTION)
S.B. CIVIL WRIT PETITION NO. ___ OF 2026

SYNOPSIS

The present writ petition arises from the complete frustration of the Petitioner's statutory right of appeal under the Recovery of Debts and Bankruptcy Act, 1993, not due to any default or delay on his part, but entirely due to administrative delays, procedural obstacles at the DRAT Registry, and institutional lapses beyond his control. The Petitioner, a borrower against whom recovery proceedings were initiated by Canara Bank, obtained a final order from the DRT Jaipur on 02.05.2023.

MEMO OF PARTIES

PETITIONER: VIRENDRA BHANDARI Son of [TO BE VERIFIED] Resident of Udaipur, Rajasthan. The Petitioner is the Borrower, Certificate Debtor and Appellant before the Debt Recovery Appellate Tribunal, Kolkata. He is a Director/Partner of M/s V.S. Bhandari Cold House Pvt. Ltd.

RESPONDENT NO. 1: CANARA BANK (Formerly Syndicate Bank) Through its Authorized Officer/Branch Manager, Udaipur, Rajasthan. The Respondent No. 1 is the Secured Creditor, Decree Holder Bank and the Applicant in Original Application No. 39 of 2013 before the Debt Recovery Tribunal, Jaipur.

RESPONDENT NO. 2: PRESIDING OFFICER DEBT RECOVERY TRIBUNAL, JAIPUR. The Respondent No. 2 is the Adjudicating Authority which passed the final order dated 02.05.2023 in OA No. 39/2013.

RESPONDENT NO. 3: REGISTRAR/APPELLATE AUTHORITY DEBT RECOVERY APPELLATE TRIBUNAL, KOLKATA. The Registrar of DRAT passed the impugned order dated 22.07.2025 in Regular Appeal Diary No. 769/2025 dismissing the Petitioner's application for waiver of statutory pre-deposit.

MOST RESPECTFULLY SHOWETH

1. That the Petitioner, Shri Virendra Bhandari, is a Director/Partner of M/s V.S. Bhandari Cold House Pvt. Ltd. which applied to the Respondent No. 1 Bank, then known as Syndicate Bank and now amalgamated with Canara Bank, on 13.05.2009 for a credit facility of Rs. 45,00,000/- for meeting working capital requirements.

2. That the Respondent No. 1 Bank sanctioned the said credit facility being an Overdraft facility (SOD Agri Indirect) of Rs. 45,00,000/- at Prime Lending Rate of 12.50% per annum vide sanction letter dated 10.06.2009. The facility was valid up to 30.06.2010. The security comprised Mortgage/Hypothecation of SICRS Book Depot and UREVA of Industrial Plot at 172-B & E-173, M.A. Road, Udaipur.

3. That in connection with the said credit facility, the Petitioner's Company executed various loan documents including a Composite Hypothecation Agreement creating a first charge in favour of the Respondent No. 1 Bank.

4. That a critical discrepancy exists in the security documents. The location of hypothecated goods is mentioned as "Factory at: B-172 (B) B-173, MIA, Udaipur" in one version of the Composite Hypothecation Agreement, while another version mentions "B-72CRJ & B173, MA, Jaipur" being a completely different location altogether. The Petitioner alleges that the Respondent No. 1 Bank committed fraud by manipulating security documents.

5. That FIR No. 0127/2015 was registered on 09.10.2015 against the officials of the Respondent No. 1 Bank under Sections 420 (Cheating) and 406 (Criminal Breach of Trust) of the Indian Penal Code, 1860 for the alleged fraudulent manipulation of security documents.

6. That the Respondent No. 1 Bank filed Original Application No. 39 of 2013 before the Debt Recovery Tribunal, Jaipur seeking recovery of debts allegedly due from the Petitioner's Company.

7. That the Debt Recovery Tribunal, Jaipur passed its final order dated 02.05.2023 in OA No. 39/2013 holding the Petitioner's Company liable to pay Rs. 53,28,346/- together with interest at the rate of 17% per annum. The DRT arbitrarily enhanced the interest rate from the sanctioned rate of 12% to 17.50% per annum, contrary to the express terms of the sanction letter.

8. That on 30.05.2024, the Petitioner wrote to the Bank requesting a One-Time Settlement. Along with the letter, the Petitioner submitted a Demand Draft dated 31.05.2024 as initial payment. Despite receiving and encashing the demand draft, the Bank cancelled and rejected the OTS vide letter dated 05.07.2024.

9. That a Recovery Certificate was issued on 16.12.2024 by the DRT Jaipur in pursuance of the order dated 02.05.2023.

10. That the Hon'ble Supreme Court delivered judgment on 16.02.2025 in Kotak Mahindra Bank Ltd. vs. Ambuj A. Kasliwal & Ors. in Civil Appeal No. 538/2021 dealing with Section 21 of the RDB Act regarding statutory pre-deposit requirement.

11. That the Hon'ble High Court of Rajasthan dismissed S.B. Civil Writ Petition No. 4548/2025 vide order dated 21.04.2025 but granted the Petitioner express liberty to file statutory appeal before DRAT challenging the DRT order.

12. That in exercise of liberty granted by the High Court, the Petitioner filed appeal bearing Diary No. 769/2025 before DRAT Delhi on 20.05.2025.

13. That the Registrar of DRAT, vide impugned order dated 22.07.2025, dismissed the Petitioner's application for waiver of statutory pre-deposit required under Section 21 of the RDB Act. The Registrar cited that mandatory deposit of 50% can be reduced to not less than 25% but cannot be waived entirely, relying upon Kotak Mahindra Bank judgment.

14. That in August 2025, the Petitioner prepared demand drafts totaling Rs. 13,25,000/- for making the pre-deposit but was unable to deposit due to non-availability of the DRAT Chairperson.

15. That the High Court of Rajasthan, vide order dated 27.10.2025 in CWP No. 16303/2025, granted liberty to the Petitioner to approach DRAT without any limitation period.

16. That despite the appellate remedy being alive, DRT Jaipur re-issued Recovery Certificate No. 241/2023 on 24.11.2025 and proceeded with coercive recovery action.

17. That on 24.12.2025, the Petitioner filed a fresh appeal before DRAT within statutory limitation under Section 20 of the RDB Act. The Petitioner prepared and tendered four fresh demand drafts for 25% pre-deposit amounting to Rs. 13,32,086/-: DD No. 368184 dated 15.12.2025; DD No. 368187 dated 20.12.2025; DD No. 035091 dated 22.12.2025; DD No. 368191 dated 06.01.2026.

18. That on 05.01.2026, a possession intimation letter was received by the Petitioner creating imminent threat of dispossession.

19. That the Petitioner filed a Chamber Appeal on 10.01.2026 before DRAT Kolkata challenging the Registrar's impugned order dated 22.07.2025.

20. That on 12.01.2026, DRT Jaipur ordered e-auction of the Petitioner's property scheduling it for 13.03.2026 while the statutory appeal remained pending.

21. That the Petitioner cured all defects raised by the DRAT Registry by 30.01.2026.

22. That on 04.02.2026, the Chamber Appeal was listed before the DRAT Chairperson but adjourned to 23.02.2026 due to administrative reasons.

23. That on 23.02.2026, the matter was again adjourned to 06.03.2026 as the mandate of the DRAT Kolkata Chairperson had expired.

24. That the Petitioner faces imminent and irreversible threat of dispossession. The e-auction is scheduled for 13.03.2026 while the Chamber Appeal hearing is on 06.03.2026, merely seven days before the auction.

GROUNDS:

A. FRUSTRATION OF STATUTORY RIGHT OF APPEAL: The statutory right of appeal under Section 20 of the RDB Act has been completely frustrated due to administrative delays, procedural obstacles at the DRAT Registry, and institutional lapses. The Petitioner has consistently demonstrated diligence at every stage.

B. VIOLATION OF NATURAL JUSTICE: The denial of opportunity to be heard in a statutory appeal violates Articles 14, 21 and 22 of the Constitution of India.

C. ILLEGALITY OF E-AUCTION DURING PENDING APPEAL: The scheduling of e-auction while the statutory appeal is pending and unheard renders the appeal illusory.

D. PRE-DEPOSIT COMPLIANCE: The Petitioner has tendered 25% pre-deposit of Rs. 13,32,086/- through four demand drafts, demonstrating bona fide compliance with Section 21.

E. ARBITRARY INTEREST RATE ENHANCEMENT: The DRT arbitrarily enhanced the interest rate from 12% to 17.50% contrary to the sanction letter.

F. SELECTIVE RECOVERY: The Bank has proceeded only against the Petitioner, ignoring other partners and directors including Mr. Surendra Bhandari, Smt. Sangeeta Bhandari, Smt. Seema Bhandari, and guarantor Shri Yashwant Paneri.

G. NON-ADJUSTMENT OF Rs. 36 LAKHS: The Bank has failed to adjust approximately Rs. 36,00,000/- received from sale of property purchased by the Petitioner's daughter Smt. Megha Bhandari.

H. DISPROPORTIONATE ATTACHMENT: The Recovery Officer proposes attachment of property measuring 12,210 sq. meters, far in excess of 5,249 sq. meters as permitted by the DRT order.

I. FRAUD BY BANK: FIR No. 0127/2015 registered against Bank officials under Sections 420 and 406 IPC for fraudulent manipulation of security documents.

SUBSTANTIAL QUESTIONS OF LAW:

(a) Whether a statutory right of appeal under Section 20 of the RDB Act can be defeated by registry delays and administrative lapses beyond the appellant's control?

(b) Whether recovery proceedings including e-auction can continue when a statutory appeal is pending and non-disposal is attributable to administrative factors?

(c) Whether denial of hearing in statutory appeal due to administrative adjournments violates Articles 14, 21 and 22 of the Constitution?

(d) Whether an auction conducted before statutory appeal is heard renders the remedy illusory and unconstitutional?

PRAYERS:

(a) Stay of e-auction scheduled for 13.03.2026 pending hearing and disposal of the Chamber Appeal before DRAT.

(b) Direction to DRAT Kolkata to hear and decide the Chamber Appeal on the next date of hearing 06.03.2026.

(c) Direction restraining DRT Jaipur from proceeding with any coercive recovery action during pendency of appeal.

(d) Direction to the Bank to adjust Rs. 36,00,000/- held from property sale proceeds.

(e) Any other appropriate relief as this Hon'ble Court may deem fit and proper.

RELIED UPON STATUTORY PROVISIONS:
- Articles 14, 21, 22, 226 and 227 of the Constitution of India
- Sections 19, 20, 21, 22, 25A, 30 of the Recovery of Debts and Bankruptcy Act, 1993
- Rules 6, 6(5) of the DRAT (Procedure) Rules, 1994
- Sections 420, 406 IPC / Sections 318, 316 BNS

RELIED UPON JUDICIAL PRECEDENTS:
- Kotak Mahindra Bank Ltd. vs. Ambuj A. Kasliwal & Ors., Civil Appeal No. 538/2021 (Supreme Court, 16.02.2025)
- Orders of Rajasthan High Court in WP No. 3726/2022, WP No. 4548/2025, and CWP No. 16303/2025
"""

BASE_URL = "http://127.0.0.1:5000"

payload = {
    "pleading_text": PLEADING_TEXT,
    "pleading_type": "WRIT_PETITION",
    "citation": "Virendra Bhandari vs Canara Bank & Ors., S.B. Civil Writ Petition 2026",
    "client_name": "Virendra Bhandari",
    "client_side": "PETITIONER",
    "opposite_party": "Canara Bank",
    "court": "Rajasthan High Court, Jaipur",
    "reliefs_sought": [
        "Stay of e-auction scheduled for 13.03.2026",
        "Direction to DRAT to hear Chamber Appeal on 06.03.2026",
        "Restraining DRT from coercive recovery action",
        "Direction to Bank to adjust Rs. 36 lakhs"
    ],
    "priority": "HIGH"
}

print("Submitting pleading to pipeline...")
print(f"URL: {BASE_URL}/api/pipeline/submit")
print(f"Pleading length: {len(PLEADING_TEXT)} characters")

resp = requests.post(f"{BASE_URL}/api/pipeline/submit", json=payload, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Response: {json.dumps(resp.json(), indent=2)}")

if resp.status_code in (200, 201, 202):
    job_id = resp.json().get("job_id")
    print(f"\nJob ID: {job_id}")
    print(f"\nCheck status at: {BASE_URL}/api/pipeline/status/{job_id}")
    print(f"View in frontend: Go to Pipeline tab and click the job")
