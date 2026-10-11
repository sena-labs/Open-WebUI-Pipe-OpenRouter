# Audit OpenRouter Pipe — 4 ottobre 2026

## Esito

**Manutenzione recente, copertura API incompleta.** Versione esaminata: `1.12.2`,
commit `f9ba1e30f3f651ed6d048f9024711d9bc0b7939b` del 3 ottobre 2026.
L'ultima release corregge ownership/cache TTS, trasporto media e compatibilità OWUI;
restano revisioni funzionali rispetto ai contratti OpenRouter attuali.

Questa è la fotografia del commit esaminato, non uno stato live del working tree.
Il seguito è tracciato nel [piano consolidato](PLAN-OPENROUTER-ALIGNMENT.md).

Obiettivo ricavato dal README: rendere il catalogo OpenRouter accessibile in Open
WebUI, con chat e media nativi, routing, reasoning, tools, preferenze personali e
trasparenza economica. Criterio per le proposte: aumentare i modelli realmente
utilizzabili e ridurre configurazioni invalide, errori e costi non visibili.

## Verifiche eseguite

| Verifica | Esito |
| --- | --- |
| `test_pipe.py` locale | **1.058 assert passati, 0 falliti** |
| `python -m unittest -v test_maintenance` locale | **16 test passati** |
| CI sul commit esaminato | Python 3.10–3.14 e smoke OWUI `v0.11.4-slim` / `main-slim`: tutti verdi |
| CodeQL sul commit esaminato | Successo |
| Guide OpenRouter e OpenAPI ufficiale | Confrontate con sorgente e payload |
| GET pubblici di discovery | Eseguiti live, senza inferenza |
| Riproduzioni di correttezza | Trasporto mock; payload e dispatch osservati |

CI consultata: [Tests](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/runs/37155470765)
e [CodeQL](https://github.com/sena-labs/Open-WebUI-Pipe-OpenRouter/actions/runs/37155470764).
Gli smoke CI verificano save/update/schema/Valves OWUI, non inferenza reale.
Le riproduzioni mock dimostrano comportamento del pipe; non misurano fatturazione
o errori reali dei provider. Nessuna generazione a pagamento eseguita nell'audit.

### Snapshot live

- `GET /api/v1/models?output_modalities=all`: **650 voci**, inclusi alias e varianti.
- Modalità: 466 text, 59 image, 30 video, 23 speech, 4 audio, 24 transcription,
  37 embeddings, 9 rerank, 13 decisions. I conteggi non sono disgiunti.
- `GET /api/v1/images/models`: **57 modelli**, tutti con `supported_parameters`
  come mappa di capability descriptors, non lista di stringhe.
- `GET /api/v1/videos/models`: **30 modelli**, con metadati specifici media.
- **334 voci** del catalogo espongono un oggetto `reasoning` per modello.
- `GET /api/frontend/all-providers`: **404**.
- `GET /api/frontend/v1/all-providers`: **200**, 92 provider.
- Catalogo generale con bearer deliberatamente invalido: **200**.
- `GET /api/v1/key` con lo stesso bearer invalido: **401**.
- Specifica ufficiale: OpenAPI **3.1.0**. Guide e schema non espongono sempre
  identici campi; validare il contratto per endpoint, evitando whitelist globali.

## Revisioni prioritarie

### 1. Alta — Merge payload e applicazione policy

Riferimenti: `openrouter_pipe.py:2554–2628`, `3336–3352`, `3737–3745`.

`_prepare_payload()` ricostruisce `provider` da zero. Quando una Valve aggiunge
almeno un campo, sostituisce l'intero oggetto esplicito del body.
Riproduzione: body con `zdr:true`, `data_collection:deny` e
`preferred_max_latency:2`, più `PROVIDER_SORT=price`, diventa solo
`provider:{sort:price}`. Anche `reasoning` viene sostituito: un effort globale
elimina `exclude`, `enabled` e altre opzioni del body.

Nel TTS, `ZDR_ENFORCE=true` e `DATA_COLLECTION=deny` non arrivano a `/audio/speech`.
La guida e lo schema TTS attuali supportano `provider.zdr`, `data_collection`
e `options`; `order`, `only`, `ignore` non si applicano a questo endpoint.
Il video esce prima della preparazione payload e ignora le policy del pipe:
OpenRouter documenta tutti gli endpoint video come retaining, quindi una policy
ZDR rigorosa deve rifiutare il submit video.

**Correzione:** merge non distruttivo, precedenze esplicite e policy restrittive
preservate. Applicazione per endpoint; non copiare automaticamente ogni campo
`provider` della chat sulle API media. Policy account/guardrail OpenRouter
continuano a essere applicate upstream: il difetto riguarda i requisiti locali
che il pipe omette o sovrascrive.

### 2. Alta — Reasoning completo nel tool loop

Riferimenti: `openrouter_pipe.py:4131–4144`, `4244–4270`, `4363–4366`.

Entrambi i tool loop ricostruiscono l'assistant message senza `reasoning_details`.
Riproduzione non-stream: un blocco `reasoning.encrypted` presente nella risposta
non compare nella richiesta successiva. Il percorso streaming non lo accumula;
inoltre reinvia `content:None`, perdendo eventuale testo del round precedente.

OpenRouter richiede il replay non modificato dei blocchi firmati/cifrati quando
necessari al modello. `<think>` visuale non sostituisce quei dati di protocollo.

**Correzione:** raccogliere e reinviare reasoning strutturato, firme e testo;
gestire delta per indice e ordine; separare display da dati per il replay.
Collaudare tool call reale sui modelli interessati dopo la regressione mock.

### 3. Alta — Image API dedicata

Riferimenti: `openrouter_pipe.py:42–48`, `1490–1540`, `1808`.

Le immagini sono materializzate dall'output `/chat/completions`, ma manca
`POST /images`. La discovery dedicata espone risoluzione, aspect ratio, qualità,
formato, numero immagini, reference e disponibilità delle preview SSE.
Il README riconosce già il limite dei modelli che richiedono `/images`.

**Revisione:** adapter Image API, discovery `/images/models` e per-endpoint;
normalizzare `data[].b64_json` / `media_type` e gli eventi di streaming in file
OWUI. Il percorso chat resta pertinente ai modelli che lo supportano: non dedurre
che tutti i modelli immagine abbiano smesso di funzionare via chat.

### 4. Alta — Identità modello, varianti e catalogo

Riferimenti: `openrouter_pipe.py:178–182`, `1315–1318`, `1490–1539`,
`1685–1693`, `1731–1771`, `2434–2530`, `2814–2826`.

- `:floor`, attivo, viene scartato come tag sconosciuto.
- `:thinking`, `:extended`, `:online` sono deprecati nella documentazione attuale.
- `_expand_variant_models()` può inventare `:free` su un modello senza relativa
  entry; le catalog variants non possono essere fabricate dal modello paid.
- Varianti virtuali speech/video finiscono su `/chat/completions`, perché il
  dispatch media confronta solo l'ID esatto originale. Riprodotto localmente.
- La risoluzione capability elimina al massimo un suffisso: combinazioni come
  `:nitro:exacto` richiedono un resolver completo.
- `decisions` non è riconosciuta: le 13 voci appaiono ma cadono nel percorso chat.
- Le entry `:batch` descrivono il Batch API, non normali conversazioni chat.
- Con sola chiave personale e chiave admin vuota, la discovery rifiuta il fetch;
  un TTS selezionato direttamente viene instradato come chat. Riprodotto.
- Metadati mancanti per preset, modelli custom o modelli esclusi dai filtri non
  dimostrano assenza di capability.

**Correzione:** separare ID richiesto da catalog ID; mantenere catalog suffix,
rimuovere soltanto routing suffix. Registry completo indipendente dai filtri
visuali, stato capability noto/sconosciuto e lookup mirati. Conservare discovery
completa con etichette chiare per modelli non invocabili nella chat.

### 5. Alta — Costo cumulativo e task media background

Riferimenti: `openrouter_pipe.py:1716–1741`, `4122–4129`, `4343–4361`.

Il tool loop mostra usage/costo solo dell'ultimo round. Due risposte mock da
`$0.02` e `$0.01` producono footer **`$0.01`**, anziché totale **`$0.03`**.
Il guard task protegge speech/video, non audio/music: `title_generation` su Lyria
viene ancora spedito con `modalities:[text,audio]`. Riprodotto il dispatch;
l'eventuale addebito effettivo non è stato misurato.

**Correzione:** usage cumulativo per turno, ID dei round/chunk, guard su tutti i
percorsi di generazione media. Single-flight delle sintesi identiche nello stesso
scope per evitare POST concorrenti duplicati. Retry di submit asincroni soltanto
con semantica che non duplichi i job.

### 6. Media — Registry icone e validazione credenziali

Riferimenti: `openrouter_pipe.py:200`, `1337–1364`.

Il vecchio registry icone restituisce 404; quello `/api/frontend/v1/all-providers`
risponde. I fallback hardcoded/SVG mitigano l'effetto visuale, ma la discovery
dinamica resta interrotta. Il catalogo pubblico con chiave invalida risponde 200:
la validazione pre-flight dichiarata nel README non è affidabile.

**Correzione:** aggiornare registry e relativo parser con fixture live; separare
catalogo pubblico da verifica autenticata `/key`, con cache per credenziale.

### 7. Media — TTS e video guidati dalle capability

Riferimenti: `openrouter_pipe.py:96`, `3479–3500`, `3740–3743`, `3794–3801`.

- Limite TTS fisso 3900 caratteri; Seed Audio 1.0 documenta 3000. Riproduzione:
  input da 3500 inviato come singolo chunk.
- Default `alloy` quando mancano voci può essere invalido. Alcuni modelli hanno
  default provider o modalità prompt/non-speech, non semplice lettura verbatim.
- Mancano reference vocali, `provider.options` e istruzioni/stile TTS.
- Video inoltra cinque parametri; mancano `frame_images`, `input_references`,
  `size`, `provider.options` e opzioni extension/upscale dove supportate.
- Polling gestisce `completed`/`failed`, non `cancelled`/`expired`.

**Revisione:** limiti e parametri per modello/endpoint, reference dagli allegati
OWUI autorizzati, messaggi chiari sulle opzioni non supportate. Conservare job ID
per recuperare risultati dopo timeout senza nuovo submit. Uno Stop upstream
richiede un endpoint di cancellazione applicabile: non prometterlo dal solo
annullamento dell'attesa locale.

### 8. Media — Web search e citazioni moderne

Riferimenti: `openrouter_pipe.py:2461–2483`, `1843–1844`, `3978–3982`,
`4223–4225`, `4466–4468`.

Plugin `web` e `:online` sono deprecati, non risultano rimossi. Migrazione
raccomandata: `tools:[{type:"openrouter:web_search"}]`. Server tools sono Beta.
Tools OWUI sovrascrivono il `tools` già presente nel body; un server tool aggiunto
insieme a funzione client viene perso. Riprodotto.
Le citazioni standard arrivano anche in `message.annotations` /
`delta.annotations` con `url_citation`; il pipe legge soltanto `citations` top-level.

**Revisione:** unione tools per identità/tipo, esecuzione locale solo delle
funzioni client, parsing annotation e rendering citazioni OWUI. Opzioni engine,
mode, domain filter e limiti chiamate/risultati; ZDR del modello non copre
automaticamente i backend dei tools.

## Migliorie di manutenzione e configurazione

- **Reasoning:** aggiungere `max`/`none` alle Valves, leggere `supported_efforts`,
  `mandatory`, `default_enabled`, `supports_max_tokens`. `include_reasoning` è
  un alias legacy; distinguere reasoning abilitato da reasoning visualizzato.
- **Routing:** Valves per `sort:{by,partition}`, soglie latency/throughput anche
  p50/p75/p90/p99, price caps image/audio/request. Lo schema include `exacto`.
- **Tier:** supportare `default`, `fast` e `ultrafast`, oltre a flex/priority;
  mostrare tier effettivo e relativa tariffa, non solo quello richiesto.
- **Compressione:** configurazione primaria con plugin `context-compression`.
  Esegue troncamento/rimozione middle-out, non riassunto semantico.
- **Costi:** valori upstream sono USD. Cambiare solo simbolo a EUR non converte
  valuta; mostrare USD oppure applicare cambio esplicito con data/fonte.
- **Concorrenza:** tools sincroni locali eseguiti ancora sul thread event loop
  (`openrouter_pipe.py:2860–2863`); offload e test di reattività dedicato.
- **Osservabilità:** `X-OpenRouter-Metadata: enabled`, modello/provider/tier
  reali, fallback, usage cumulativo e ID generazione; quota chiave oltre a credito
  account. `session_id` OpenRouter va distinto dal dato interno OWUI oggi rimosso.
- **CI anti-drift:** GET discovery e fixture/snapshot schema aggiornati,
  regressioni sulle capability e probe live read-only schedulato. Conteggi
  catalogo variabili: non bloccare CI su un numero fisso di modelli.
- **Struttura:** registry capability, payload/policy e adapter media separati
  internamente; mantenere artefatto distribuibile single-file per installazione
  OWUI. Evitare un refactor globale come prerequisito delle patch puntuali.

## Nuove feature consigliate

| Priorità | Feature | Valore per il pipe |
| --- | --- | --- |
| Alta | Immagini native Image API | Più modelli utilizzabili, image-to-image/editing, ratio, qualità, quantità e preview supportate |
| Alta | Profili per modello | Effort, voce, risoluzione e routing persistenti per modello; filtri capability e stato utilizzabile/discovery-only |
| Alta | Server tools selezionabili | Web search/fetch, datetime e generazione immagini nella normale chat; limiti di uso/spesa espliciti |
| Media | STT dagli allegati | `/audio/transcriptions`, lingua, timestamp e speaker dove supportati |
| Media | Reference audio/video | Voice cloning/design, first/last frame e reference-to-video; controlli aderenti al provider |
| Media | Pannello costo/routing | Totale turno, provider/modello/tier reale, cache HIT/MISS, tentativi e job recuperabili |
| Media | Presets e router selezionabili | `@preset/...`, profili condivisi, shortlist Auto/Free/Pareto/Switchyard senza capability gating errato |
| Media | Response cache opt-in | `X-OpenRouter-Cache`, TTL e bypass; distinta da prompt cache e cache TTS; scope utenti e replay tools considerati |
| Bassa | Adapter Responses opzionale | Reasoning e tools specifici; storia completa nel client, API stateless: `store:true` / `previous_response_id` non utilizzabili |

Embeddings/rerank hanno maggiore utilità nelle connessioni RAG native OWUI che
come risposta chat. Gestione chiavi/workspace/batch è meno prioritaria del
completamento dei percorsi di inferenza e media già promessi dal prodotto.

## Sequenza di rilascio suggerita

1. **Patch di correttezza:** merge/policy, reasoning replay, resolver varianti,
   task/costi, registry/auth e stati terminali media. Regression test sui casi
   riprodotti; collaudo reale mirato dei provider interessati.
2. **Release funzionale:** Image API, capability registry e web server tools,
   parsing citazioni e Valves moderne.
3. **Estensioni UX/media:** STT e reference, profili/presets, diagnostica e cache.

Trade-off: solo manutenzione lascia incompleto il catalogo media; una riscrittura
totale aumenta rischio e ritarda i fix. Consigliata evoluzione incrementale per
adapter/capability, con regressioni e artefatto OWUI single-file.

## Fonti ufficiali

- [API changelog](https://openrouter.ai/docs/changelog.md)
- [OpenAPI](https://raw.githubusercontent.com/OpenRouterTeam/docs/main/openapi/openapi.yaml)
- [Models](https://openrouter.ai/docs/guides/overview/models.md)
- [Reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens.md)
- [Model variants](https://openrouter.ai/docs/guides/routing/model-variants/overview.md)
- [Image API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation.md)
- [Video API](https://openrouter.ai/docs/guides/overview/multimodal/video-generation.md)
- [TTS](https://openrouter.ai/docs/guides/overview/multimodal/tts.md)
- [STT](https://openrouter.ai/docs/guides/overview/multimodal/stt.md)
- [Plugins e deprecazioni web](https://openrouter.ai/docs/guides/features/plugins.md)
- [Web search server tool](https://openrouter.ai/docs/guides/features/server-tools/web-search.md)
- [ZDR](https://openrouter.ai/docs/guides/features/zdr.md)
- [BYOK e limitazioni ZDR video](https://openrouter.ai/docs/guides/overview/auth/byok.md)
- [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection.md)
- [Service tiers](https://openrouter.ai/docs/guides/features/service-tiers.md)
- [Context compression](https://openrouter.ai/docs/guides/features/message-transforms.md)
- [Router metadata](https://openrouter.ai/docs/guides/features/router-metadata.md)
- [Response cache](https://openrouter.ai/docs/guides/features/response-caching.md)
- [Presets](https://openrouter.ai/docs/guides/features/presets.md)
- [Responses API stateless](https://openrouter.ai/docs/api_reference/responses/overview.md)
