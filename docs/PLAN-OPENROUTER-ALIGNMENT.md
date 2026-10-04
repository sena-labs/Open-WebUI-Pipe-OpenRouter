# Allineamento OpenRouter — piano consolidato

Data: 2026-10-04. Base: `v1.12.2`, commit `f9ba1e3`.

## Obiettivo e stato

Rendere il catalogo OpenRouter realmente utilizzabile in Open WebUI, con
contratti per endpoint, policy preservate, reasoning/tools corretti, media
nativi e costo completo del turno.

Sessione operativa: quella del subentro e consolidamento. La sessione
`ses_efd12e13afferN4HckQDxtIbVg` ha concluso il turno ed è sorgente storica di
audit/pianificazione, non un secondo flusso di implementazione.

Questo documento è il riferimento della roadmap e sostituisce la proposta
locale `.opencode/plans/openrouter-alignment.md`, ignorata da Git.
Evidenze e fonti: [audit](OPENROUTER-AUDIT-2026-10-04.md).

L'utente ha richiesto tre fasi e scelto «pianificazione prima». La roadmap
comprende tutte e tre; l'esecuzione procede per deliverable verificabili.
Il design della prima fase viene presentato prima delle modifiche al prodotto.

### Avanzamento

- Subentro e consolidamento completati; utente ha approvato «Avvia Fase 1».
- Fase 1 implementata e verificata, con regressioni e documentazione aggiornata.
  Inclusa correzione aggiuntiva del filtro free: discovery
  live ha mostrato 5 modelli immagine a pagamento con prezzi token `0/0`.
- Fasi 2 e 3 mantengono il perimetro sotto descritto; gli adapter nuovi richiedono
  il rispettivo design prima dell'implementazione.

### Evidenze Fase 1

| Verifica | Esito |
| --- | --- |
| `test_pipe.py` | 1.058 assert, 0 falliti |
| `unittest test_maintenance test_alignment` | 55 test, 0 falliti; 39 nuove regressioni alignment |
| Smoke OWUI `v0.11.4-slim` | Create/update, schema admin/user, persistenza Valves e rimozione funzione: PASS |
| Smoke OWUI `main-slim` | Stesse verifiche: PASS; image digest `sha256:e8adae70e1db7a838d5d6cdfe2a66a4c1d293a0361b304ccc20df179b17aeead` |
| Discovery usando il pipe aggiornato senza chiave admin | 650 voci, 23 speech, 30 video; tipi non-chat classificati |
| Registry icone usando il pipe aggiornato | 108 chiavi incluse alias; fetch pubblico riuscito |

Inferenza/media verificati con mock; discovery con GET pubblici. Gli smoke
verificano il loader OWUI, non una generazione reale sui provider. Collaudi
provider a pagamento restano una verifica separata con budget concordato.

## Impostazione

- Evoluzione incrementale dei flussi esistenti, con adapter/capability separati
  quando vengono aggiunti nuovi endpoint.
- Installazione OWUI tramite un solo `openrouter_pipe.py`.
- Verifiche locali con trasporto mock; discovery/schema tramite GET read-only.
- Collaudi di inferenza/media con budget definito prima della loro esecuzione.
- Versione di release determinata dal contenuto effettivo e dalla compatibilità:
  il confronto `v1.13`/`v2.0` non blocca la preparazione tecnica.

## Fase 1 — Correttezza dell'integrazione esistente

| Deliverable | Comportamento atteso | Evidenza di chiusura |
| --- | --- | --- |
| Payload e policy | Merge `provider`/`reasoning` non distruttivo; precedenze documentate; nessun indebolimento dei requisiti privacy applicabili | Payload mock conserva `zdr`, `data_collection`, `exclude` e opzioni compatibili insieme ai default |
| Privacy media | TTS inoltra solo policy/options supportate; video rifiutato quando ZDR rigoroso richiesto | Payload TTS corretto; nessun submit video in caso di policy incompatibile |
| Reasoning/tools | Replay completo `reasoning_details` e contenuto assistant; raccolta delta; tools client/server preservati; callable sync off-loop | Round successivo conserva blocchi opachi; tools misti non persi; test reattività event loop |
| Accounting del turno | Usage e costo cumulativi, ID per round/chunk, indicazione valuta coerente con USD upstream | Fixture `$0.02 + $0.01` mostra `$0.03`; altri percorsi mantengono accounting corretto |
| Identità/capability | Catalog ID distinto dall'ID richiesto; metadata completi indipendenti dai filtri visuali; stato sconosciuto distinto da assenza capability | Routing speech/video/audio per varianti corretto; preset/custom non degradati senza evidenza |
| Discovery/auth | Catalogo pubblico separato da credenziale effettiva; `/key` per validazione; registry icone aggiornato | Chiave invalida rilevata; sola chiave personale funziona; fixture registry attuale interpretata |
| Task media | Background tasks non avviano generazioni media a pagamento | Fixture task speech/video/audio e percorsi immagine interessati con zero submit di generazione |
| Robustezza media | Stati `cancelled`/`expired` terminali; limiti TTS per modello; default voce corretti; job identificabile dopo timeout | Fixture stati terminali; Seed Audio non supera 3000 caratteri; nessun nuovo submit per recuperare un job |

### Correzioni rispetto al piano ereditato

1. **Varianti:** rimuovere soltanto routing suffix per leggere metadata;
   preservare catalog suffix. Non trasformare `model:free` nel modello paid.
   `:free` è selezionabile soltanto se esiste; `:batch` è discovery-only nella chat.
   `:floor` è riconosciuto; le varianti deprecate non sono alias intercambiabili
   da rimappare automaticamente senza mantenere la semantica del modello.
2. **Media:** non generare indiscriminatamente varianti per endpoint che non le
   supportano. Quando una variante/alias è supportata, usare metadata risolti per
   scegliere l'adapter e preservare l'ID richiesto nel contratto applicabile.
3. **Sessioni:** distinguere `session_id` interno OWUI da sessione OpenRouter.
   Non rimuovere la protezione dei campi interni con un semplice passthrough.
   Mapping esplicito/pseudonimo per raggruppamento, con scope utente/chat.
4. **Privacy:** policy per endpoint. Le opzioni routing della chat non sono tutte
   valide per speech/video. Lo stesso vale per cache fingerprint quando cambia
   la policy applicabile a una sintesi.
5. **Web:** mantenere nella Fase 1 la preservazione dei tools già forniti.
   Migrazione plugin `web`/`:online`, selettore server tools e nuove citazioni
   sono un unico deliverable funzionale della Fase 2, non due implementazioni.
6. **Reasoning:** effort e budget rispettano metadata per modello; `mandatory`
   impedisce un disable invalido. Merge non significa inviare combinazioni
   incompatibili di parametri.

Chiusura Fase 1: regressioni significative dei casi auditati; `test_pipe.py` e
`test_maintenance` verdi; smoke save/update/schema su OWUI pulito; documentazione
delle precedenze e dei comportamenti aggiornata. Test mock e collaudi provider
sono evidenze distinte.

## Fase 2 — Endpoint e funzionalità moderne

| Deliverable | Output | Evidenza di chiusura |
| --- | --- | --- |
| Image API | Adapter `POST /images`, reference/editing, parametri per endpoint e preview supportate; file nativi OWUI | Fixture buffered/SSE/error e reference; rendering OWUI; collaudo reale mirato |
| Capability e profili | Registry normalizzato per chat/image/video/speech; informazioni picker e impostazioni per modello | Fixture discovery reale, opzioni non supportate rilevate, profili isolati |
| Valves moderne | Effort, tier, sort/partition, soglie performance, price caps e context-compression | Payload aderenti ai singoli contratti e migrazione compatibile delle impostazioni |
| Server tools/web | Tools selezionabili, unione per identità, parsing annotations/citazioni, limiti di uso e configurazioni engine | Tools client/server convivono; citazioni OWUI corrette; limiti verificati |

Prima dell'implementazione degli adapter nuovi, precisare e approvare input,
output, errori, rendering e compatibilità della rispettiva integrazione.

## Fase 3 — Estensioni richieste

| Deliverable | Output | Evidenza di chiusura |
| --- | --- | --- |
| STT | Trascrizione dagli allegati, lingua, timestamp e speaker dove supportati | Accesso allegati autorizzato; fixture formati/limiti; risultato OWUI |
| Reference media | First/last frame video, reference-to-video, voice cloning/design e stile | Payload e capability provider-specifici; file/input accessibili nel corretto scope |
| Presets/router | Presets e shortlist selezionabili senza capability gating errato | ID/configurazioni preservati; modello effettivo visibile |
| Diagnostica/cache | Provider/modello/tier, fallback, totale turno, job recuperabili; response cache opt-in con TTL/bypass | HIT/MISS corretti, scope utenti, replay tools e recupero senza submit duplicati |

Responses, embeddings/rerank come integrazione RAG e Batch/gestione workspace
restano proposte separate dell'audit, non prerequisiti delle tre fasi richieste.

## Verifiche anti-drift

Estendere CI con discovery/schema read-only e fixture controllate per endpoint.
Non fissare il numero dei modelli come condizione di successo: il catalogo
cambia. Conservare matrix Python, smoke OWUI e controlli già presenti.

## Sequenza

Policy/payload → reasoning/tools e accounting → resolver/discovery → guard e
robustezza media → chiusura Fase 1 → adapter/capability e web della Fase 2 →
estensioni della Fase 3.
