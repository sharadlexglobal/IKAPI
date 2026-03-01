"""
Taxonomy Seed Script — analyzes existing genomes and populates categories, topics, and provision index.
Run once to initialize, safe to re-run (upsert logic).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from db import (
    get_db_connection, init_db,
    upsert_taxonomy_category, upsert_taxonomy_topic, upsert_provision,
)

CATEGORIES = {
    "CAT_NI_ACT": {
        "name": "Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "description": "Cheque dishonour under Section 138, complaints, presumptions, vicarious liability of directors, limitation, and related procedural issues.",
    },
    "CAT_CRPC": {
        "name": "Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "description": "Criminal procedural law — quashing under S.482, cognizance, complaints, revision, inherent powers of High Court.",
    },
    "CAT_CPC": {
        "name": "Code of Civil Procedure, 1908",
        "parent_statute": "Code of Civil Procedure, 1908",
        "description": "Civil procedural law — execution, revision, jurisdiction, limitation in civil matters.",
    },
    "CAT_CONSTITUTION": {
        "name": "Constitution of India",
        "parent_statute": "Constitution of India",
        "description": "Constitutional provisions — Article 226/227 writ jurisdiction, Article 136 SLP, fundamental rights, principles of natural justice.",
    },
    "CAT_IPC": {
        "name": "Indian Penal Code, 1860",
        "parent_statute": "Indian Penal Code, 1860",
        "description": "Substantive criminal offences — cheating (S.420), criminal breach of trust (S.405-406), conspiracy (S.120B).",
    },
    "CAT_EVIDENCE": {
        "name": "Indian Evidence Act, 1872",
        "parent_statute": "Indian Evidence Act, 1872",
        "description": "Law of evidence — presumptions, admissibility, burden of proof.",
    },
    "CAT_LIMITATION": {
        "name": "Limitation Act, 1963",
        "parent_statute": "Limitation Act, 1963",
        "description": "Law of limitation — computation of period, condonation of delay, exclusion of time.",
    },
    "CAT_TPA": {
        "name": "Transfer of Property Act, 1882",
        "parent_statute": "Transfer of Property Act, 1882",
        "description": "Transfer of immovable property — sale, mortgage, lis pendens, power of attorney sales.",
    },
    "CAT_CONTRACT": {
        "name": "Indian Contract Act, 1872",
        "parent_statute": "Indian Contract Act, 1872",
        "description": "Law of contracts — consideration, void agreements, agency.",
    },
    "CAT_SARFAESI": {
        "name": "SARFAESI Act, 2002",
        "parent_statute": "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act, 2002",
        "description": "Securitisation, asset reconstruction, enforcement of security interest, DRT appeals.",
    },
    "CAT_RDB": {
        "name": "Recovery of Debts Act, 1993",
        "parent_statute": "Recovery of Debts Due to Banks and Financial Institutions Act, 1993",
        "description": "DRT/DRAT proceedings, recovery certificates, natural justice in debt recovery.",
    },
    "CAT_PCA": {
        "name": "Prevention of Corruption Act, 1988",
        "parent_statute": "Prevention of Corruption Act, 1988",
        "description": "Criminal misconduct by public servants, sanction for prosecution, disproportionate assets.",
    },
    "CAT_GCA": {
        "name": "General Clauses Act, 1897",
        "parent_statute": "General Clauses Act, 1897",
        "description": "Interpretive provisions — computation of time, service of notice, meanings of standard expressions.",
    },
    "CAT_ARBITRATION": {
        "name": "Arbitration and Conciliation Act, 1996",
        "parent_statute": "Arbitration and Conciliation Act, 1996",
        "description": "Arbitration proceedings, challenge of awards, enforcement, interim measures.",
    },
    "CAT_POA": {
        "name": "Powers of Attorney Act, 1882",
        "parent_statute": "Powers of Attorney Act, 1882",
        "description": "Execution and validity of powers of attorney, GPA/SPA sales.",
    },
    "CAT_IT_ACT": {
        "name": "Income Tax Act, 1961",
        "parent_statute": "Income Tax Act, 1961",
        "description": "Income tax proceedings, recovery, cash transaction limits.",
    },
    "CAT_SFC": {
        "name": "State Financial Corporations Act, 1951",
        "parent_statute": "State Financial Corporations Act, 1951",
        "description": "State financial corporations, loan recovery, property seizure.",
    },
}

TOPICS = {
    "TOP_NI138_DISHONOUR": {
        "category_id": "CAT_NI_ACT",
        "name": "Dishonour of Cheque — Section 138",
        "description": "Core offence of cheque dishonour, elements of the offence, ingredients to be proved.",
        "keywords": ["dishonour", "cheque bounce", "section 138", "insufficient funds", "payment stopped", "account closed", "cheque returned"],
    },
    "TOP_NI138_NOTICE": {
        "category_id": "CAT_NI_ACT",
        "name": "Legal Notice — Service and Validity",
        "description": "Demand notice under proviso (b) to S.138, service requirements, deemed service, refusal of notice.",
        "keywords": ["legal notice", "demand notice", "service of notice", "deemed service", "refused notice", "returned unserved", "15 days", "proviso b", "cause of action"],
    },
    "TOP_NI138_PRESUMPTION": {
        "category_id": "CAT_NI_ACT",
        "name": "Presumption under Section 139",
        "description": "Statutory presumption of legally enforceable debt, burden on accused to rebut, standard of proof.",
        "keywords": ["presumption", "section 139", "legally enforceable debt", "burden of proof", "preponderance of probability", "rebuttal", "discharge of onus"],
    },
    "TOP_NI138_DIRECTORS": {
        "category_id": "CAT_NI_ACT",
        "name": "Vicarious Liability — Directors under Section 141",
        "description": "Liability of company directors, persons in charge, nominee directors, sleeping directors.",
        "keywords": ["section 141", "vicarious liability", "director", "person in charge", "company", "responsible", "nominee director", "managing director"],
    },
    "TOP_NI138_COMPLAINT": {
        "category_id": "CAT_NI_ACT",
        "name": "Complaint Filing and Limitation",
        "description": "Section 142 complaint requirements, one-month limitation, cognizance, premature complaint.",
        "keywords": ["section 142", "complaint", "limitation", "one month", "30 days", "premature", "cognizance", "cause of action", "filing"],
    },
    "TOP_NI138_JURISDICTION": {
        "category_id": "CAT_NI_ACT",
        "name": "Territorial Jurisdiction",
        "description": "Jurisdiction for S.138 complaints — place of dishonour, place of presentation, K. Bhaskaran.",
        "keywords": ["jurisdiction", "territorial", "place of dishonour", "place of presentation", "place of drawing", "place of payment", "k bhaskaran", "situs"],
    },
    "TOP_NI138_COMPENSATION": {
        "category_id": "CAT_NI_ACT",
        "name": "Compensation and Sentencing",
        "description": "Interim compensation under S.143A, final compensation under S.357, sentencing patterns.",
        "keywords": ["compensation", "interim compensation", "section 143a", "sentencing", "fine", "imprisonment", "section 357", "double the cheque amount"],
    },
    "TOP_NI138_COMPOUNDING": {
        "category_id": "CAT_NI_ACT",
        "name": "Compounding of Offence",
        "description": "Compounding under S.147, settlement, acquittal on compounding, mediation.",
        "keywords": ["compounding", "section 147", "settlement", "compromise", "acquittal", "mediation"],
    },
    "TOP_NI138_DEBT": {
        "category_id": "CAT_NI_ACT",
        "name": "Legally Enforceable Debt or Liability",
        "description": "Nature of underlying debt/liability, gift cheques, security cheques, blank cheques.",
        "keywords": ["legally enforceable debt", "liability", "consideration", "gift cheque", "security cheque", "blank cheque", "loan", "debt"],
    },
    "TOP_CRPC_QUASHING": {
        "category_id": "CAT_CRPC",
        "name": "Quashing under Section 482 CrPC",
        "description": "Inherent powers of High Court to quash criminal proceedings, FIR quashing, abuse of process.",
        "keywords": ["quashing", "section 482", "inherent powers", "abuse of process", "no offence made out", "frivolous", "vexatious", "fir quashing"],
    },
    "TOP_CRPC_COGNIZANCE": {
        "category_id": "CAT_CRPC",
        "name": "Cognizance and Process",
        "description": "Taking cognizance under S.190, issuance of process under S.204, pre-summoning stage.",
        "keywords": ["cognizance", "section 190", "section 204", "process", "summoning", "issuance", "prima facie", "complaint examination"],
    },
    "TOP_CRPC_REVISION": {
        "category_id": "CAT_CRPC",
        "name": "Criminal Revision",
        "description": "Revisional jurisdiction under S.397/401, scope of revision, interlocutory orders.",
        "keywords": ["revision", "section 397", "section 401", "revisional", "interlocutory", "supervisory jurisdiction"],
    },
    "TOP_CRPC_JOINDER": {
        "category_id": "CAT_CRPC",
        "name": "Addition of Accused — Section 319",
        "description": "Power to add accused during trial, evidence during inquiry, summoning additional persons.",
        "keywords": ["section 319", "addition of accused", "summoning", "additional accused", "joinder"],
    },
    "TOP_CRPC_DOUBLE_JEOPARDY": {
        "category_id": "CAT_CRPC",
        "name": "Double Jeopardy — Section 300",
        "description": "Protection against double prosecution, autrefois acquit/convict.",
        "keywords": ["double jeopardy", "section 300", "autrefois", "previously acquitted", "previously convicted", "same offence"],
    },
    "TOP_CONST_ART226": {
        "category_id": "CAT_CONSTITUTION",
        "name": "Writ Jurisdiction — Article 226/227",
        "description": "High Court writ jurisdiction, certiorari, mandamus, prohibition, habeas corpus, quo warranto.",
        "keywords": ["article 226", "article 227", "writ", "certiorari", "mandamus", "prohibition", "habeas corpus", "writ petition", "judicial review"],
    },
    "TOP_CONST_ART136": {
        "category_id": "CAT_CONSTITUTION",
        "name": "Special Leave Petition — Article 136",
        "description": "Supreme Court SLP jurisdiction, leave to appeal, scope of interference.",
        "keywords": ["article 136", "special leave", "slp", "leave to appeal", "supreme court", "interference"],
    },
    "TOP_CONST_NATURAL_JUSTICE": {
        "category_id": "CAT_CONSTITUTION",
        "name": "Natural Justice and Fair Hearing",
        "description": "Audi alteram partem, right to hearing, bias, reasonable opportunity, Article 14/21.",
        "keywords": ["natural justice", "audi alteram partem", "fair hearing", "right to be heard", "reasonable opportunity", "bias", "article 14", "article 21"],
    },
    "TOP_CPC_EXECUTION": {
        "category_id": "CAT_CPC",
        "name": "Execution of Decrees",
        "description": "Order 21 proceedings, attachment, sale, obstruction, third party claims.",
        "keywords": ["execution", "order 21", "decree", "attachment", "sale", "obstruction", "third party", "judgment debtor"],
    },
    "TOP_CPC_JURISDICTION": {
        "category_id": "CAT_CPC",
        "name": "Civil Court Jurisdiction",
        "description": "Pecuniary and territorial jurisdiction, Section 9 bar, inherent lack of jurisdiction.",
        "keywords": ["jurisdiction", "section 9", "pecuniary", "territorial", "civil court", "competent court"],
    },
    "TOP_CPC_REVISION": {
        "category_id": "CAT_CPC",
        "name": "Civil Revision — Section 115",
        "description": "Revisional jurisdiction of High Court in civil matters, jurisdictional error.",
        "keywords": ["revision", "section 115", "revisional", "jurisdictional error", "material irregularity"],
    },
    "TOP_LIMITATION_CONDONATION": {
        "category_id": "CAT_LIMITATION",
        "name": "Condonation of Delay",
        "description": "Section 5 power to condone delay, sufficient cause, liberal construction.",
        "keywords": ["condonation", "delay", "section 5", "sufficient cause", "liberal", "condone"],
    },
    "TOP_LIMITATION_COMPUTATION": {
        "category_id": "CAT_LIMITATION",
        "name": "Computation of Limitation Period",
        "description": "Exclusion of time, starting point, Section 12, Section 14, Section 15.",
        "keywords": ["computation", "limitation period", "exclusion", "section 12", "section 14", "starting point", "accrual"],
    },
    "TOP_IPC_CHEATING": {
        "category_id": "CAT_IPC",
        "name": "Cheating and Criminal Breach of Trust",
        "description": "Section 420 cheating, Section 405/406 CBT, dishonest inducement, entrustment.",
        "keywords": ["cheating", "section 420", "section 405", "section 406", "criminal breach of trust", "dishonest", "inducement", "entrustment"],
    },
    "TOP_SARFAESI_ENFORCEMENT": {
        "category_id": "CAT_SARFAESI",
        "name": "Security Interest Enforcement",
        "description": "Section 13 proceedings, possession, sale of secured assets, DRT appeals under S.17/18.",
        "keywords": ["sarfaesi", "section 13", "possession", "secured asset", "enforcement", "security interest", "section 17", "section 18"],
    },
    "TOP_RDB_RECOVERY": {
        "category_id": "CAT_RDB",
        "name": "DRT/DRAT Recovery Proceedings",
        "description": "Recovery of debts, recovery certificates, DRT jurisdiction, appeals to DRAT.",
        "keywords": ["drt", "drat", "recovery", "tribunal", "recovery certificate", "debt recovery", "section 19"],
    },
    "TOP_POA_VALIDITY": {
        "category_id": "CAT_POA",
        "name": "Power of Attorney — Validity and Scope",
        "description": "GPA/SPA sales, validity of POA transactions, Suraj Lamp Industries.",
        "keywords": ["power of attorney", "gpa", "spa", "suraj lamp", "attorney", "delegation"],
    },
    "TOP_GCA_SERVICE": {
        "category_id": "CAT_GCA",
        "name": "Service and Computation of Time",
        "description": "Section 27 GCA — deemed service by post, computation of time periods.",
        "keywords": ["general clauses act", "section 27", "deemed service", "service by post", "computation of time"],
    },
    "TOP_PCA_SANCTION": {
        "category_id": "CAT_PCA",
        "name": "Sanction for Prosecution",
        "description": "Requirement of prior sanction, Section 19 PCA, valid sanctioning authority.",
        "keywords": ["sanction", "prosecution", "section 19", "sanctioning authority", "prevention of corruption"],
    },
}

PROVISION_MAP = {
    "NI_ACT_S138": {
        "canonical_name": "Section 138, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S138", "NIA_S138", "S138_NIA", "S138_NI_Act", "NI_ACT_S138", "S138_NIA_1881", "NIA_S138_PROVISO_A", "NIA_S138_PROVISO_B", "S138b_NI_Act"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S139": {
        "canonical_name": "Section 139, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S139", "NIA_S139", "S139_NIA"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S140": {
        "canonical_name": "Section 140, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S140", "NIA_S140"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S141": {
        "canonical_name": "Section 141, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S141", "NIA_S141", "S141_NI_Act"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S142": {
        "canonical_name": "Section 142, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S142", "NIA_S142", "S142_NIA"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S143A": {
        "canonical_name": "Section 143A, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S143A", "NIA_S143A"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S147": {
        "canonical_name": "Section 147, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S147", "NIA_S147"],
        "category_id": "CAT_NI_ACT",
    },
    "NI_ACT_S56": {
        "canonical_name": "Section 56, Negotiable Instruments Act, 1881",
        "parent_statute": "Negotiable Instruments Act, 1881",
        "aliases": ["NI_S56", "S56_NI_Act"],
        "category_id": "CAT_NI_ACT",
    },
    "CRPC_S482": {
        "canonical_name": "Section 482, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S482", "CrPC_S482", "CrPC_482", "S482_CRPC", "S482_CrPC"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S190": {
        "canonical_name": "Section 190, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S190", "CrPC_S190", "CrPC_190"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S200": {
        "canonical_name": "Section 200, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S200", "CrPC_S200", "CrPC_200", "S200_CrPC"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S204": {
        "canonical_name": "Section 204, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S204", "CrPC_S204"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S319": {
        "canonical_name": "Section 319, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S319", "CrPC_S319"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S300": {
        "canonical_name": "Section 300, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S300"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S397": {
        "canonical_name": "Section 397/401, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S397", "CrPC_S397", "CrPC_397_401"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S173": {
        "canonical_name": "Section 173, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S173", "CrPC_S173"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S156": {
        "canonical_name": "Section 156, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CrPC_S156"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S255": {
        "canonical_name": "Section 255, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S255_1"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S258": {
        "canonical_name": "Section 258, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S258"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S357": {
        "canonical_name": "Section 357, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S357_1", "CRPC_S357_3", "CrPC_S421_S357"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S468": {
        "canonical_name": "Section 468, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S468_2_C", "S473_CRPC", "CRPC_S472"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S2D": {
        "canonical_name": "Section 2(d), Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S2D", "CRPC_S2_N", "CrPC_S2d", "CrPC_2n_offence", "S2(d)_CRPC"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S177": {
        "canonical_name": "Section 177-179, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CrPC_S177", "CrPC_S178", "CrPC_S179"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S203": {
        "canonical_name": "Section 203, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CrPC_203"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S207": {
        "canonical_name": "Section 207, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CrPC_S207"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S239": {
        "canonical_name": "Section 239, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CrPC_S239"],
        "category_id": "CAT_CRPC",
    },
    "CRPC_S313": {
        "canonical_name": "Section 313, Code of Criminal Procedure, 1973",
        "parent_statute": "Code of Criminal Procedure, 1973",
        "aliases": ["CRPC_S313"],
        "category_id": "CAT_CRPC",
    },
    "CONST_ART226": {
        "canonical_name": "Article 226, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART226", "CONST_ART_226", "CONSTITUTION_ART226_227"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART227": {
        "canonical_name": "Article 227, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART227", "CONST_ART_227"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART136": {
        "canonical_name": "Article 136, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART136", "CONST_ART_136"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART137": {
        "canonical_name": "Article 137, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONST_ART_137"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART142": {
        "canonical_name": "Article 142, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART142"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART14": {
        "canonical_name": "Article 14, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART14", "CONST_ART_14"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART21": {
        "canonical_name": "Article 21, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART21"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART32": {
        "canonical_name": "Article 32, Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONST_ART_32"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART19": {
        "canonical_name": "Article 19(1), Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONST_ART_19_1"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CONST_ART20": {
        "canonical_name": "Article 20(2), Constitution of India",
        "parent_statute": "Constitution of India",
        "aliases": ["CONSTITUTION_ART_20_2"],
        "category_id": "CAT_CONSTITUTION",
    },
    "CPC_O21": {
        "canonical_name": "Order 21, Code of Civil Procedure, 1908",
        "parent_statute": "Code of Civil Procedure, 1908",
        "aliases": ["CPC_O3R1R2"],
        "category_id": "CAT_CPC",
    },
    "CPC_S115": {
        "canonical_name": "Section 115, Code of Civil Procedure, 1908",
        "parent_statute": "Code of Civil Procedure, 1908",
        "aliases": ["CPC_S115"],
        "category_id": "CAT_CPC",
    },
    "CPC_S152": {
        "canonical_name": "Section 152, Code of Civil Procedure, 1908",
        "parent_statute": "Code of Civil Procedure, 1908",
        "aliases": ["CPC_S152"],
        "category_id": "CAT_CPC",
    },
    "CPC_S20": {
        "canonical_name": "Section 20, Code of Civil Procedure, 1908",
        "parent_statute": "Code of Civil Procedure, 1908",
        "aliases": ["CPC_S20"],
        "category_id": "CAT_CPC",
    },
    "IPC_S420": {
        "canonical_name": "Section 420, Indian Penal Code, 1860",
        "parent_statute": "Indian Penal Code, 1860",
        "aliases": ["IPC_S420", "S420_IPC", "IPC_S415"],
        "category_id": "CAT_IPC",
    },
    "IPC_S406": {
        "canonical_name": "Section 405/406, Indian Penal Code, 1860",
        "parent_statute": "Indian Penal Code, 1860",
        "aliases": ["IPC_S405", "IPC_S406"],
        "category_id": "CAT_IPC",
    },
    "IPC_S120B": {
        "canonical_name": "Section 120B, Indian Penal Code, 1860",
        "parent_statute": "Indian Penal Code, 1860",
        "aliases": ["IPC_S120B_409_420", "IPC_S420_467_468_471"],
        "category_id": "CAT_IPC",
    },
    "LIMITATION_S5": {
        "canonical_name": "Section 5, Limitation Act, 1963",
        "parent_statute": "Limitation Act, 1963",
        "aliases": ["S5_LimitationAct", "LA_12", "LA_12_1_2"],
        "category_id": "CAT_LIMITATION",
    },
    "LIMITATION_S3": {
        "canonical_name": "Section 3, Limitation Act, 1963",
        "parent_statute": "Limitation Act, 1963",
        "aliases": ["S3_LimitationAct", "S2(b)_LimitationAct", "S29(2)_LimitationAct"],
        "category_id": "CAT_LIMITATION",
    },
    "SARFAESI_S13": {
        "canonical_name": "Section 13, SARFAESI Act, 2002",
        "parent_statute": "SARFAESI Act, 2002",
        "aliases": ["SARFAESI_S13_2"],
        "category_id": "CAT_SARFAESI",
    },
    "SARFAESI_S18": {
        "canonical_name": "Section 18, SARFAESI Act, 2002",
        "parent_statute": "SARFAESI Act, 2002",
        "aliases": ["SARFAESI_S18_PROVISO_III"],
        "category_id": "CAT_SARFAESI",
    },
    "RDB_S19": {
        "canonical_name": "Section 19, Recovery of Debts Act, 1993",
        "parent_statute": "Recovery of Debts Act, 1993",
        "aliases": ["RDDBFI_S19", "RDDBFI_S26_2"],
        "category_id": "CAT_RDB",
    },
    "PCA_S13": {
        "canonical_name": "Section 13, Prevention of Corruption Act, 1988",
        "parent_statute": "Prevention of Corruption Act, 1988",
        "aliases": ["PCA_S13_1c_1d", "PCA_S4_ss4"],
        "category_id": "CAT_PCA",
    },
    "PCA_S19": {
        "canonical_name": "Section 19, Prevention of Corruption Act, 1988",
        "parent_statute": "Prevention of Corruption Act, 1988",
        "aliases": ["PCA_S19", "PCA_S22_d"],
        "category_id": "CAT_PCA",
    },
    "GCA_S27": {
        "canonical_name": "Section 27, General Clauses Act, 1897",
        "parent_statute": "General Clauses Act, 1897",
        "aliases": ["GCA_S27", "S27_GCA", "GCA_9"],
        "category_id": "CAT_GCA",
    },
    "TPA_S52": {
        "canonical_name": "Section 52, Transfer of Property Act, 1882",
        "parent_statute": "Transfer of Property Act, 1882",
        "aliases": ["Section 52"],
        "category_id": "CAT_TPA",
    },
    "POA_S2": {
        "canonical_name": "Section 2, Powers of Attorney Act, 1882",
        "parent_statute": "Powers of Attorney Act, 1882",
        "aliases": ["POA_ACT_S2"],
        "category_id": "CAT_POA",
    },
    "EVIDENCE_S114": {
        "canonical_name": "Section 114 Illustration (f), Indian Evidence Act, 1872",
        "parent_statute": "Indian Evidence Act, 1872",
        "aliases": ["IEA_S114_ILLUS_F", "EVIDENCE_ACT_S60"],
        "category_id": "CAT_EVIDENCE",
    },
    "CONTRACT_S23": {
        "canonical_name": "Section 23/24, Indian Contract Act, 1872",
        "parent_statute": "Indian Contract Act, 1872",
        "aliases": ["CONTRACT_ACT_SS23_24", "CONTRACT_ACT_S183"],
        "category_id": "CAT_CONTRACT",
    },
}

STATUTE_TO_CATEGORY = {
    "negotiable instruments act": "CAT_NI_ACT",
    "ni act": "CAT_NI_ACT",
    "code of criminal procedure": "CAT_CRPC",
    "crpc": "CAT_CRPC",
    "code of civil procedure": "CAT_CPC",
    "cpc": "CAT_CPC",
    "constitution of india": "CAT_CONSTITUTION",
    "constitution": "CAT_CONSTITUTION",
    "indian penal code": "CAT_IPC",
    "ipc": "CAT_IPC",
    "indian evidence act": "CAT_EVIDENCE",
    "evidence act": "CAT_EVIDENCE",
    "limitation act": "CAT_LIMITATION",
    "transfer of property act": "CAT_TPA",
    "tpa": "CAT_TPA",
    "indian contract act": "CAT_CONTRACT",
    "contract act": "CAT_CONTRACT",
    "sarfaesi": "CAT_SARFAESI",
    "securitisation": "CAT_SARFAESI",
    "recovery of debts": "CAT_RDB",
    "rddbfi": "CAT_RDB",
    "rdb act": "CAT_RDB",
    "prevention of corruption": "CAT_PCA",
    "general clauses act": "CAT_GCA",
    "arbitration": "CAT_ARBITRATION",
    "power of attorney": "CAT_POA",
    "powers of attorney": "CAT_POA",
    "income tax act": "CAT_IT_ACT",
    "state financial corporations": "CAT_SFC",
    "industrial disputes act": "CAT_NI_ACT",
    "bengal money lenders": "CAT_CONTRACT",
}


def seed_categories():
    print("Seeding categories...")
    for cat_id, data in CATEGORIES.items():
        upsert_taxonomy_category(cat_id, data["name"], data["parent_statute"], data["description"])
        print(f"  {cat_id}: {data['name']}")
    print(f"  Total: {len(CATEGORIES)} categories")


def seed_topics():
    print("Seeding topics...")
    for topic_id, data in TOPICS.items():
        upsert_taxonomy_topic(topic_id, data["category_id"], data["name"], data["description"], data["keywords"])
        print(f"  {topic_id}: {data['name']}")
    print(f"  Total: {len(TOPICS)} topics")


def seed_provisions():
    print("Seeding provision index...")
    for prov_id, data in PROVISION_MAP.items():
        upsert_provision(prov_id, data["canonical_name"], data["parent_statute"],
                         data["aliases"], data["category_id"])
        print(f"  {prov_id}: {data['canonical_name']} ({len(data['aliases'])} aliases)")
    print(f"  Total: {len(PROVISION_MAP)} canonical provisions")


def statute_to_category(statute_text):
    if not statute_text:
        return None
    s = statute_text.lower().strip()
    for key, cat_id in STATUTE_TO_CATEGORY.items():
        if key in s:
            return cat_id
    return None


def run_seed():
    print("=== Taxonomy Seed Script ===\n")
    init_db()
    seed_categories()
    print()
    seed_topics()
    print()
    seed_provisions()
    print("\n=== Seed complete ===")


if __name__ == "__main__":
    run_seed()
