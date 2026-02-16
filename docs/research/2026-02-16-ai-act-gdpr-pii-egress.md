# Research: AI Act + GDPR for Optional PII Filter on LLM Egress

Date: 2026-02-16
Scope: Klargora vad "PII" betyder i EU-ratt (AI Act + GDPR) och hur det bor mappas till ett valbart filter vid skickning av data till externa LLM:er.

## Sources
- AI Act (Regulation (EU) 2024/1689), Official Journal text:
  - https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng
- GDPR (Regulation (EU) 2016/679), consolidated text:
  - https://eur-lex.europa.eu/legal-content/en/TXT/?uri=CELEX%3A02016R0679-20160504
- European Commission AI Act policy page (timeline + implementation updates):
  - https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- EDPB opinion on AI models (2024-12-18):
  - https://www.edpb.europa.eu/news/news/2024/edpb-opinion-ai-models-gdpr-principles-support-responsible-ai_en
- EDPB pseudonymisation update (2025-01-17):
  - https://www.edpb.europa.eu/news/news/2025/edpb-adopts-pseudonymisation-guidelines-and-paves-way-improve-cooperation_en

## Key legal takeaways

### 1) "PII" i EU = "personal data" (personuppgifter)
- GDPR Article 4(1): personuppgifter ar all information som relaterar till en identifierad eller identifierbar fysisk person.
- Slutsats: i EU-baserad policy bor vi anvanda termen `personal data` som huvudterm och `PII` som praktisk alias.

### 2) Kansliga kategorier ar striktare
- GDPR Article 9: sarskilda kategorier (t.ex. etnicitet, politiska asikter, religion, biometriska data for unik identifiering, halsa, sexliv/sexuell laggning) ar i grunden forbjudna att behandla utan undantag.
- GDPR Article 10: uppgifter om brottsdomar/brott kraver sarskild rattslig grund och skydd.

### 3) AI Act ersatter inte GDPR
- AI Act Article 2(7): dataskyddsregler (GDPR m.fl.) fortsatter att galla; AI Act paverkar inte dem, med specificerade undantag/lex-specialis-punkter.
- Praktiskt: AI Act + GDPR maste tolkas tillsammans.

### 4) AI Act har tydliga regler nar kansliga data far hanteras i AI-kontext
- AI Act Article 10(5): for high-risk-system kan behandling av sarskilda kategorier tillatas for bias-detektion/-korrektion, men bara med strikta villkor (nodvandighet, skydd, pseudonymisering, borttagning, accesskontroller).
- AI Act Article 59: vidarebehandling av persondata i AI-sandbox ar tillaten endast under tydliga offentligintressevillkor och med harda safeguards.
- AI Act Article 5(1)(g): vissa biometriska kategoriseringsanvandningar ar uttryckligen forbudna.

### 5) Pseudonymisering ar inte anonymisering
- EDPB (2025): pseudonymiserade data ar fortfarande personuppgifter om de kan aterkopplas via tillaggsinformation.
- EDPB (2024 AI-opinion): "anonymt" for AI-modeller kravs hog traskel och bedoms fall-for-fall.

### 6) Tidslinje (status per 2026-02-16)
- AI Act tradde i kraft 2024-08-01.
- Forbud/AI literacy borjade galla 2025-02-02.
- Merparten av reglerna galler fran 2026-08-02 (med vissa undantag till 2027-08-02).
- Kommissionen har ocksa kommunicerat forenklingsforslag; lagtext i kraft ar dock fortsatt huvudkallan for compliance-beslut.

## Relevance to Aurora

### Journalistik-lage du beskrev (bevara full data internt)
- Det ar kompatibelt med en EU-linje om:
  - tydlig purpose/laglig grund,
  - scope-isolering,
  - audit trail och accesskontroll,
  - och styrd egress till externa LLM:er.

### Praktisk policy-arkitektur (rekommenderad)
1. `storage_policy=full_fidelity` internt (inga automatiska redaction i karnlagret).
2. `egress_policy` separat, tillampas endast vid outbound till LLM.
3. Egress-lagen:
   - `off`: ingen maskning.
   - `pseudonymize`: ersatt identifierare med stabila tokens.
   - `redact`: maska definierade kategorier.
4. `policy_reason_codes` pa varje egress-beslut, t.ex.:
   - `allow.full_fidelity_internal`
   - `transform.pseudonymize_email`
   - `transform.redact_special_category`
5. Logga exakt vilken policy som anvandes per request/model/provider.

## Minimal PII taxonomy for optional egress filter
- Direct identifiers: namn, e-post, telefon, personnummer/id-nummer, kontonummer.
- Online/location identifiers: IP, device-id, exakta koordinater, online-id.
- Special categories (GDPR Art. 9): etnicitet, religion, politik, biometrik for unik identifiering, halsa, sexliv/sexuell laggning.
- Criminal-offence data (GDPR Art. 10): domar/brottsrelaterade uppgifter.

## Suggested next steps
1. Definiera `egress_policy` i config (default `off` for ditt journalistiska lage, med explicit toggle).
2. Inför `policy_reason_codes` i outbound path och run_log.
3. Lägg till provider-profiler (vilka endpoints far `off` respektive krav pa `pseudonymize/redact`).
4. Bygg testfall for tre moden (`off`, `pseudonymize`, `redact`) med golden fixtures.

## Notes
- Detta ar en teknisk policy-sammanfattning, inte juridisk radgivning.
