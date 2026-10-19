# Phase C.1: Donor Dataset & ML Feasibility Audit Report

**Project:** LifeLink — AI-Powered Emergency Healthcare Intelligence & Response Network  
**Phase:** C.1 — Donor Dataset and Machine Learning Feasibility Audit  
**Author:** Senior Machine Learning Engineer & Data Engineer  
**Date:** October 9, 2026  
**Status:** Audit Complete — Clear Recommendations Defined  

---

## 1. Executive Summary

This audit evaluates the feasibility of developing machine learning capabilities for the LifeLink emergency blood donation response system, using the dataset:
- `LifeLink_Realistic_Synthetic_30K_Donors.csv` (7,473,595 bytes, 30,000 rows, 28 columns)
- Requested notebook: `blood-donation-dataset.ipynb` (Missing from repository and system paths)

### Key Findings:
1. **Nature of the Data:** The 30,000-record dataset is **100% synthetic**. It represents a static registry of synthetic donor profiles and medical screening answers.
2. **Missing Ground-Truth for Core ML Goal (Response/Ranking):** The dataset contains **no emergency dispatch logs**, **no donor response outcomes** (accepted/declined), **no response latency records**, and **no paired emergency-donor interactions**. Therefore, training a donor response model or ranking model directly on this CSV without creating fake labels is **statistically impossible**.
3. **Synthetic Eligibility Label Analysis:** The dataset contains one candidate target: `Eligible_for_Donation` (`Yes`: 77.02%, `No`: 22.98%). However, this label was generated through **deterministic logical rules** (`Hemoglobin < 12.5`, `Fever == 'Yes'`, `Infection == 'Yes'`, `Recent_Surgery == 'Yes'`, `Medical_Condition == 'Anemia'`).
4. **Clinical & Engineering Verdict:**
   - Replacing deterministic blood donor eligibility screening with a probabilistic ML classifier is **clinically hazardous and redundant**. Medical eligibility must remain governed by deterministic clinical rule engines.
   - The true high-value machine learning task for LifeLink is **Donor Emergency Response Probability Ranking** ($P(\text{Response} \mid \text{Donor}, \text{Distance}, \text{Emergency Context})$).
   - To build this model without fabricating data, LifeLink must log real or realistically simulated emergency dispatch interaction sessions.

---

## 2. Dataset Structure

* **File Path:** `d:\Life link 🖤🖤\LifeLink_Realistic_Synthetic_30K_Donors.csv`
* **Format:** Comma-Separated Values (CSV), UTF-8 encoded
* **File Size:** 7,473,595 bytes (~7.13 MB)
* **Total Rows:** 30,000 records
* **Total Columns:** 28 columns

### Column Inventory & Data Types:

| # | Column Name | Inferred Type | Non-Null Count | Null % | Unique | Description / Scope |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `Donor_ID` | String | 30,000 | 0.00% | 30,000 | Primary key identifier (LLD-000001 to LLD-030000) |
| 2 | `Full_Name` | String | 30,000 | 0.00% | 2,220 | Synthetic personal names |
| 3 | `Gender` | String | 30,000 | 0.00% | 2 | 'Male', 'Female' |
| 4 | `Age` | Int64 | 30,000 | 0.00% | 48 | Integer ages (18 to 65 years) |
| 5 | `Blood_Group` | String | 30,000 | 0.00% | 8 | O+, B+, A+, AB+, O-, B-, A-, AB- |
| 6 | `Contact_Number` | String | 30,000 | 0.00% | 30,000 | Synthetic telephone contact numbers |
| 7 | `Email` | String | 30,000 | 0.00% | 29,786 | Synthetic email addresses |
| 8 | `City` | String | 30,000 | 0.00% | 30 | Major Indian urban centers |
| 9 | `State` | String | 30,000 | 0.00% | 12 | State designations |
| 10 | `Country` | String | 30,000 | 0.00% | 1 | Constant ('India') |
| 11 | `Last_Donation_Date` | String (Date) | 15,264 | 49.12% | 1,156 | Date of previous donation (null for first-time donors) |
| 12 | `Total_Donations` | Int64 | 30,000 | 0.00% | 13 | Count of lifetime donations (0 to 12) |
| 13 | `Eligible_for_Donation`| String (Cat) | 30,000 | 0.00% | 2 | Candidate label ('Yes' / 'No') |
| 14 | `Medical_Condition` | String (Cat) | 3,506 | 88.31% | 5 | Anemia, Asthma, Diabetes, Hypertension, Thyroid disorder |
| 15 | `Weight_kg` | Float64 | 30,000 | 0.00% | 543 | Body weight (45.0 to 110.0 kg) |
| 16 | `Hemoglobin_g_dL` | Float64 | 30,000 | 0.00% | 79 | Hemoglobin measurement (10.0 to 17.8 g/dL) |
| 17 | `Donation_Center` | String | 30,000 | 0.00% | 45 | Assigned blood center / bank |
| 18 | `Registration_Date` | String (Date) | 30,000 | 0.00% | 3,071 | Profile creation date (2018-03-18 to 2026-08-13) |
| 19 | `Tattooed` | String (Cat) | 30,000 | 0.00% | 2 | 'Yes', 'No' |
| 20 | `Tattoo_Date` | String (Date) | 4,729 | 84.24% | 2,406 | Date tattoo was acquired |
| 21 | `Recently_Donated` | String (Cat) | 30,000 | 0.00% | 2 | 'Yes', 'No' |
| 22 | `Taking_Medicine` | String (Cat) | 30,000 | 0.00% | 2 | 'Yes', 'No' |
| 23 | `Medicine_Type` | String (Cat) | 9,654 | 67.82% | 7 | Category of medication |
| 24 | `Fever` | String (Cat) | 30,000 | 0.00% | 2 | Active fever self-report ('Yes', 'No') |
| 25 | `Infection` | String (Cat) | 30,000 | 0.00% | 2 | Active infection self-report ('Yes', 'No') |
| 26 | `Recent_Surgery` | String (Cat) | 30,000 | 0.00% | 2 | Recent surgical procedure ('Yes', 'No') |
| 27 | `Availability` | String (Cat) | 30,000 | 0.00% | 3 | 'Available', 'On-call', 'Unavailable' |
| 28 | `Eligibility_Reason` | String | 30,000 | 0.00% | 54 | Explanation of eligibility / disqualification reason |

---

## 3. Data-Quality Findings

### A. Missing Values
* `Last_Donation_Date`: 14,736 missing (49.12%). Consistent with `Total_Donations == 0`.
* `Medical_Condition`: 26,494 missing (88.31%). Null represents "No pre-existing chronic conditions".
* `Tattoo_Date`: 25,271 missing (84.24%). Exactly mirrors `Tattooed == 'No'`.
* `Medicine_Type`: 20,346 missing (67.82%). Exactly mirrors `Taking_Medicine == 'No'`.

### B. Duplicate Checks
* **Exact Duplicate Rows:** 0 across all 28 columns.
* **Duplicate `Donor_ID`:** 0. All 30,000 identifiers are unique.
* **Duplicate Synthetic Emails:** 214 collisions due to simple `{firstname}.{lastname}{num}@example.com` synthetic generator logic.

### C. Distributions & Numerical Integrity
* **Age:** Minimum 18, Maximum 65, Mean 32.83, Median 33.0, Std 9.35. Matches Indian standard donor age limits (18–65).
* **Weight:** Minimum 45.0 kg, Maximum 110.0 kg, Mean 65.58 kg. Matches minimum donation weight threshold (45.0 kg).
* **Hemoglobin:** Minimum 10.0 g/dL, Maximum 17.8 g/dL, Mean 13.89 g/dL.
* **Blood Group Frequencies:**
  * O+: 11,236 (37.45%)
  * B+: 9,947 (33.16%)
  * A+: 6,415 (21.38%)
  * AB+: 1,215 (4.05%)
  * O-: 439 (1.46%)
  * B-: 377 (1.26%)
  * A-: 250 (0.83%)
  * AB-: 121 (0.40%)
  *(Closely models real-world South Asian blood group distributions).*

---

## 4. Candidate Prediction Targets

| Target Candidate | Available? | Type | Distribution | Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **A. Donor Eligibility Classification** (`Eligible_for_Donation`) | **Yes** | Binary ('Yes' / 'No') | Yes: 23,107 (77.02%)<br>No: 6,893 (22.98%) | **Synthetic deterministic label.** Generated via programmatic rule checks. While a classifier can be trained, deploying ML for clinical eligibility creates clinical hazards and offers no benefit over deterministic boolean rules. |
| **B. Donor Response Prediction** | **No** | Binary | N/A | **Unavailable in dataset.** There is no column tracking SOS alert acceptance, response time, or attendance. |
| **C. Donor Matching / Ranking Quality** | **No** | Numerical / Ranking | N/A | **Unavailable in dataset.** There are no paired emergency interaction records, ranking ground truths, or relevance feedback. |

---

## 5. Data Leakage Risks

If one were to train a classifier on `Eligible_for_Donation`, severe data leakage would occur unless multiple features are stripped:

1. **Direct Outcome Leakage (`Eligibility_Reason`):**
   * If `Eligibility_Reason == "Eligible for prototype matching"`, label is 100% `Yes`.
   * If `Eligibility_Reason` contains any string such as `"Hemoglobin below prototype threshold"`, label is 100% `No`.
2. **Post-Screening Status Leakage (`Availability`):**
   * Cross-tabulation proves that `Availability == 'Unavailable'` occurs **only** when `Eligible_for_Donation == 'No'` (6,893 / 6,893 cases, 100% correlation).
   * Any model including `Availability` achieves trivial 100% accuracy through target leakage.
3. **Deterministic Generator Inputs:**
   * `Hemoglobin_g_dL < 12.5`: 100% of records in this range are `No` (2,812 donors).
   * `Fever == 'Yes'`: 100% are `No` (778 donors).
   * `Infection == 'Yes'`: 100% are `No` (1,055 donors).
   * `Recent_Surgery == 'Yes'`: 100% are `No` (507 donors).
   * `Recently_Donated == 'Yes'`: 100% are `No` (606 donors).
   * `Medical_Condition == 'Anemia'`: 100% are `No` (448 donors).

A tree or regression model trained on these variables would simply memorize the synthetic generator's `if/else` conditionals, giving a false appearance of high machine learning intelligence.

---

## 6. Review of the Existing Application

### Architecture Inspection:
* **Controller Route:** `GET /api/v1/blood/donors/ranked?emergencyId={id}` ([backend/app/api/v1/blood.py](file:///d:/Life%20link%20%F0%9F%96%A4%F0%9F%96%A4/backend/app/api/v1/blood.py))
* **Service Implementation:** `DonorService.get_ranked_donors()` ([backend/app/services/donor_service.py](file:///d:/Life%20link%20%F0%9F%96%A4%F0%9F%96%A4/backend/app/services/donor_service.py))
* **Current Ranking Logic:**
  1. Blood Compatibility Filter: Matches emergency recipient blood group with exact matches or universal `O-`.
  2. Candidate Order: Uses `order_by(Donor.ai_rank.asc())` with fallback to seeded heuristic ranks.
  3. Dynamic Search Config: Returns search radius rings (2 km initial, 5 km current, 15 km max).
  4. Explicit Metadata Flag: Returns `aiRecommendation` noting that ranking is currently heuristic rule-based and ML is not yet configured.

### Non-Negotiable Safety Safeguards in Current Code:
1. **Consent Verification:** In `DonorService.contact_donor()`, the system queries `Consent.emergency_communication`. If ungranted, it denies contact with HTTP 403 Forbidden and writes an audit log.
2. **Medical Eligibility Gate:** Contact is strictly blocked if `donor.eligibility == 'ineligible'` or `status in ['declined', 'unavailable']` with HTTP 400 Bad Request.
3. **Audit Trail:** Every blocked or successful contact decision is recorded in `audit_logs`.

---

## 7. Recommended Machine Learning Strategy

### What NOT to do:
* **Do NOT replace clinical eligibility rules with ML:** Eligibility guidelines (Hb ≥ 12.5, no active infection, weight ≥ 45 kg, cooldown period) must remain **100% deterministic**. An ML model with 98% accuracy implies a 2% error rate, which could dangerously dispatch an anemic or infected donor to an emergency center.

### What to build (Recommended Task):
* **Task:** **Donor Emergency Response Probability Ranking**
* **Formulation:** Supervised binary classification or Learning-to-Rank (`LambdaMART`).
* **Objective:** Predict $P(\text{Response} = 1 \mid \text{Donor Attributes}, \text{Emergency Context}, \text{Spatio-Temporal Context})$.
* **Formula:**
  $$\text{Final Rank Score} = w_1 \cdot \hat{P}(\text{Response}) + w_2 \cdot (1 - \text{Normalized Distance}) + w_3 \cdot \text{Historical Reliability}$$

### Bridging the Ground-Truth Gap:
Since the static 30K CSV has no interaction logs, LifeLink must generate an **Emergency Interaction Event Log** connecting donors to simulated emergency calls:
* Features needed:
  1. `Emergency_ID` & `Urgency_Level`
  2. `Donor_ID` & static demographics (`Age`, `Blood_Group`, `Total_Donations`)
  3. `Distance_Km` (donor location to requesting hospital)
  4. `Time_Of_Day` (e.g., night vs. daytime calls)
  5. `Day_Of_Week` (weekend vs. weekday availability)
  6. **True Outcome Label:** `Responded` (1 = Accepted, 0 = Ignored/Declined) & `Response_Latency_Minutes`.

### Baseline Models & Metrics:
* **Baselines:**
  1. Heuristic distance/cooldown ranker (current production baseline).
  2. Regularized Logistic Regression (interpretable linear baseline).
* **Proposed Production Model:** **XGBoost Classifier / CatBoost Classifier**.
* **Primary Evaluation Metrics:**
  * **PR-AUC (Precision-Recall AUC):** Vital due to class imbalance in emergency response rates.
  * **Expected Calibration Error (ECE):** Crucial to ensure predicted response probabilities represent true empirical frequencies.
  * **NDCG@5 / Precision@3:** Evaluates whether the top 3–5 contacted donors are likely to respond.
  * *(Accuracy is explicitly rejected as a sole metric due to severe base-rate skew).*

---

## 8. Privacy, Ethics & Healthcare Safety

1. **PII Isolation:** Full names, phone numbers, and email addresses must be stripped during feature engineering. Training must operate solely on hashed or synthetic identifiers (`Donor_ID`).
2. **Fairness & Demographic Parity:** Models must not systematically deprioritize protected demographic groups when blood compatibility is satisfied.
3. **Strict Fallback Architecture:** If the ML service fails, times out, or returns low confidence, the backend must seamlessly fall back to the existing deterministic distance/compatibility ranking without interrupting emergency operations.

---

## 9. Next Implementation Steps (Phase C.2 Roadmap)

1. **Create Interaction Simulation / Event Logger:** Build an event generator or schema for `Emergency_Donor_Interactions` that links the 30K donors to realistic emergency dispatches with distance, time-of-day, and response outcomes.
2. **Implement Feature Pipeline:** Build an automated pre-processor computing geospatial distances, donation intervals, and historical response rates.
3. **Train & Validate Models:** Train Logistic Regression (baseline) and XGBoost (candidate), evaluating PR-AUC and NDCG@5 with 5-fold cross-validation.
4. **Export Model Artifacts:** Serialize model weights and feature scalers to `backend/app/ai/models/` without breaking any existing production endpoints.

---

*Report certified by Senior ML & Data Engineering Team.*
