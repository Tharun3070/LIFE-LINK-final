# LifeLink AI / ML Architecture Specification

## Overview
LifeLink's AI intelligence consists of three core specialized modules:
1. **LLM Intent Parser**: Extracts structured emergency metadata, blood requirements, organ urgency, and notes from clinical requests.
2. **Authorized RAG Retrieval**: Secure, role-gated retrieval of eligible donor records, compatibility facts, and medical guidelines. **Never gives unrestricted raw database access to the LLM.**
3. **XGBoost Donor Ranking**: Machine learning ranking model predicting response probability, reliability score, and reachability score.

## Phase 1 Status: Clean Architectural Foundation
In Phase 1, these AI components are represented by typed abstract interfaces (`interfaces.py`).
- No fake predictions are misrepresented as real ML.
- Developer stubs explicitly declare placeholder behavior.
- Real model integration, weights, and inference pipelines are scheduled for Phase 4 (XGBoost) and Phase 5 (RAG + LLM).
