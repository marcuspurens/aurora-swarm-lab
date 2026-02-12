# Research: "ralph-loop" prompt runner (inspirerad av Anthropic-demo)

## Syfte
En "prompt runner" är en kontrollslinga som kör en uppgift i flera iterationer
tills en tydlig completion-signal uppnås. Det ger reproducerbara resultat och
mindre "flum" än en öppen chat.

## Vad bilden indikerar
- Ett kommando som tar en prompt: `/ralph-loop "Build a REST API for todos."`
- Krav anges i prompten: CRUD, validering, tester.
- En explicit completion-promise: `<promise>COMPLETE</promise>`
- En max-iteration flagga: `--max-iterations 50`

Detta liknar en "agent loop" med hårda kriterier för stopp.

## Designmål (om vi bygger något liknande)
- **Determinism**: samma input -> nära samma output.
- **Completion signal**: strikt "promise" så vi vet när jobbet är klart.
- **Max iterations**: skydd mot oändlig loop.
- **Policy**: begränsa verktyg, filsystem, nätverk efter behov.
- **Rapportering**: logga iterationer, ändringar, testresultat.

## Kärnkomponenter
1) **Prompt template**
   - Beskrivning + krav + "completion promise".
2) **Loop controller**
   - Upprepar `plan -> act -> verify`.
   - Stoppar när completion-signal uppnås eller max-iter.
3) **Verifiering**
   - Tester, lint, eller explicit check.
4) **Output formatter**
   - Sammanfattning + artifacts + logg.

## Förslag på gränssnitt
CLI-exempel:
```
aurora loop "Build a REST API for todos." \
  --requirements "CRUD, input validation, tests" \
  --completion-promise "COMPLETE" \
  --max-iterations 50
```

MCP-exempel:
```
tool: loop_run
args: { prompt, requirements, completion_promise, max_iterations }
```

## Risker och mitigering
- **Loopar fast** -> `max-iterations` + timeout.
- **Missar krav** -> explicit verifiering (tests/lint).
- **För mycket förändring** -> diff-gräns + rollback-policy.

## Relevans för Aurora
Användbart för:
- "Bygg X och verifiera Y"
- Automatisera repetitiva transformationsjobb
- Batch‑uppgifter (t.ex. sammanfatta varje ny föreläsning)

Inte nödvändigt för daglig ingest/chat-workflow, men bra för "projekt-uppgifter".

## Nästa steg (om vi implementerar)
1) Definiera en minimal loop‑API (CLI + MCP).
2) Implementera verifierings‑hook (test/health).
3) Logga iterationer och avslutssignal.
