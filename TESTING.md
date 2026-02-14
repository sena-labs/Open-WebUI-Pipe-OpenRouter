# Pre-Release Testing Guide

Checklist manuale per verificare ogni funzionalità del Pipe prima della release.

> **Prerequisiti**: Open WebUI ≥ 0.4.0 in esecuzione, API key OpenRouter valida.

---

## 0. Test automatici

```bash
python test_pipe.py
```

Deve stampare **170/170 passed**. Se qualche test fallisce, **non rilasciare**.

---

## 1. Installazione e caricamento

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 1.1 | Copia il contenuto di `openrouter_pipe.py` nella sezione **Functions → Pipe** di Open WebUI | Nessun errore, la pipe viene salvata |
| 1.2 | Apri **Admin → Settings → Connections** e verifica che la pipe compaia | Tipo **manifold**, icona SVG viola visibile |
| 1.3 | Seleziona la pipe e apri **Valves** | Tutti i campi configurabili sono visibili con i default corretti |

---

## 2. API Key e lista modelli

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 2.1 | Lascia `OPENROUTER_API_KEY` vuoto → apri il selettore modelli | Appare un unico modello "error" con messaggio `API key not configured` |
| 2.2 | Inserisci una chiave valida nelle Valves → riapri il selettore | I modelli OpenRouter compaiono (340+ modelli), ognuno con l'icona del provider |
| 2.3 | Inserisci una chiave **invalida** (es. `sk-fake`) → riapri il selettore | Appare un modello "error" con messaggio `Invalid API key (HTTP ...)`. La validazione avviene tramite `/auth/key` |

---

## 3. Chat non-streaming

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 3.1 | Seleziona un modello (es. `openai/gpt-4o`), scrivi "Hello" con `stream: false` | La risposta compare tutta insieme, testo corretto |
| 3.2 | Seleziona un modello reasoning (es. `anthropic/claude-3.7-sonnet:thinking`) | La risposta contiene i blocchi `<think>...</think>` seguiti dal contenuto |

---

## 4. Chat streaming (SSE)

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 4.1 | Seleziona un modello, scrivi "Tell me a story" con stream attivo | Il testo appare token per token in tempo reale |
| 4.2 | Usa un modello reasoning in streaming | Tag `<think>` aperto, reasoning progressivo, `</think>` chiuso, poi contenuto |
| 4.3 | Durante lo streaming, verifica nella Network tab che ogni chunk SSE inizi con `data: ` | Formato SSE corretto |

---

## 5. Reasoning tokens

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 5.1 | Imposta `INCLUDE_REASONING = true` (default) | Il payload contiene `"include_reasoning": true` |
| 5.2 | Imposta `INCLUDE_REASONING = false` | Il campo `include_reasoning` **non** compare nel payload |
| 5.3 | Imposta `REASONING_EFFORT = high` | Il payload contiene `"reasoning": {"effort": "high"}` |
| 5.4 | Imposta `REASONING_EFFORT = ""` (vuoto) | Nessun campo `reasoning` nel payload |
| 5.5 | Prova con effort `low`, `medium`, `high` | Accettati. Qualsiasi altro valore viene ignorato |

---

## 6. Provider routing

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 6.1 | Imposta `PROVIDER_SORT = throughput` | payload → `provider.sort = "throughput"` |
| 6.2 | Imposta `PROVIDER_ORDER = anthropic, openai` | payload → `provider.order = ["anthropic", "openai"]` |
| 6.3 | Imposta `PROVIDER_IGNORE = google` | payload → `provider.ignore = ["google"]` |
| 6.4 | Imposta `REQUIRE_PARAMETERS = true` | payload → `provider.require_parameters = true` |
| 6.5 | Imposta `DATA_COLLECTION = deny` | payload → `provider.data_collection = "deny"` |
| 6.6 | Lascia tutti vuoti/default | Nessun campo `provider` nel payload |

---

## 7. Filtro modelli

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 7.1 | Imposta `MODEL_PROVIDERS = openai` | Solo modelli OpenAI visibili nel selettore |
| 7.2 | Imposta `MODEL_PROVIDERS = openai` + `INVERT_PROVIDER_LIST = true` | Tutti i modelli **tranne** OpenAI visibili |
| 7.3 | Imposta `MODEL_PROVIDERS = ALL` o svuota il campo | **Tutti** i modelli tornano visibili. Il default `ALL` indica nessun filtro |
| 7.4 | Imposta `FREE_ONLY = true` | Solo modelli gratuiti (compresi quelli con pricing 0/0 senza suffisso `:free`) |
| 7.5 | `FREE_ONLY = true` → verifica che `google/gemma-*` o `qwen/qwen3-*` gratis compaiano | I modelli senza `:free` ma con pricing 0/0 sono inclusi |

---

## 8. Prefisso modelli

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 8.1 | Imposta `MODEL_PREFIX = "🔥 "` | Tutti i nomi modello iniziano con `🔥 ` nel selettore |
| 8.2 | Svuota `MODEL_PREFIX` | Nomi modello senza prefisso (l'UI permette di svuotare il campo) |

---

## 9. Fallback models

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 9.1 | Imposta `FALLBACK_MODELS = openai/gpt-4o, anthropic/claude-3.5-sonnet` | payload → `"models": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]` |
| 9.2 | Lascia `FALLBACK_MODELS` vuoto | Nessun campo `models` nel payload |

---

## 10. Middle-out compression

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 10.1 | Imposta `ENABLE_MIDDLE_OUT = true` | payload → `"transforms": ["middle-out"]` |
| 10.2 | `ENABLE_MIDDLE_OUT = false` | Nessun campo `transforms` nel payload |

---

## 11. Cache control (Anthropic)

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 11.1 | Imposta `ENABLE_CACHE_CONTROL = true`, invia un prompt lungo con content di tipo lista | Il chunk di testo più lungo riceve `"cache_control": {"type": "ephemeral"}` |
| 11.2 | `ENABLE_CACHE_CONTROL = false` | Nessuna modifica ai messaggi |
| 11.3 | Invia un messaggio con content stringa semplice + cache attivo | Nessun crash, cache non applicata (solo per content di tipo lista) |

---

## 12. Retry logic

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 12.1 | Imposta `MAX_RETRIES = 2`, simula un timeout temporaneo del server | La pipe ritenta fino a 3 tentativi totali (1 + 2 retry), poi mostra errore |
| 12.2 | Verifica nei log `[OpenRouter Pipe] Attempt X failed:` | I log mostrano ogni tentativo fallito |
| 12.3 | Un errore HTTP 4xx (es. 401) **non** viene ritentato | Errore restituito immediatamente senza retry |

---

## 13. Timeout

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 13.1 | Imposta `REQUEST_TIMEOUT = 5` (secondi), invia un prompt a un modello lento | Dopo 5s compare `timeout` nel messaggio di errore |
| 13.2 | Imposta `REQUEST_TIMEOUT = -1` | Errore di validazione Pydantic: non si salva nelle valves |
| 13.3 | Default `REQUEST_TIMEOUT = 90` | Funziona normalmente senza timeout prematuri |

---

## 14. Gestione errori

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 14.1 | Invia un prompt che causa errore API (es. modello inesistente) | Messaggio `OpenRouter Pipe Error: HTTP 4xx - ...` |
| 14.2 | Stream con errore mid-stream (es. context_length_exceeded) | Il contenuto parziale è preservato, poi appare il messaggio di errore |
| 14.3 | Stream con `<think>` aperto + errore | `</think>` viene chiuso automaticamente prima del messaggio di errore |

---

## 15. Citations

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 15.1 | Usa un modello che restituisce citations (es. con web search plugin) | I riferimenti `[1]`, `[2]` nel testo sono convertiti in link markdown `[[1]](url)` |
| 15.2 | La sezione `Citations:` appare alla fine della risposta | Lista numerata di URL |
| 15.3 | Stream con citations in chunk separato | Le citations sono applicate correttamente anche alle porzioni successive |

---

## 16. Headers e sicurezza

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 16.1 | Nella Network tab, verifica gli header della richiesta | `Authorization: Bearer sk-or-...`, `HTTP-Referer`, `X-Title`, `Content-Type` |
| 16.2 | Verifica che l'API key **non** compaia mai nei log o nei messaggi di errore | Solo errori generici, mai il valore della chiave |
| 16.3 | Verifica che nessun campo interno Open WebUI (`chat_id`, `title`, `task`, `features`) sia nel payload | Tutti rimossi prima dell'invio |

---

## 17. Icone provider

| # | Azione | Risultato atteso |
|---|--------|------------------|
| 17.1 | Apri il selettore modelli | I modelli di OpenAI, Anthropic, Google, Meta, ecc. mostrano la propria icona |
| 17.2 | Verifica un provider sconosciuto (es. `aion-labs`) | Nessuna icona (campo vuoto), nessun errore |

---

## Riepilogo veloce pre-release

```
[ ] python test_pipe.py → 170/170 ✓
[ ] python integration_test.py → 47/47 ✓
[ ] API key vuota → errore chiaro
[ ] API key valida → 340+ modelli
[ ] Chat non-streaming funziona
[ ] Chat streaming funziona (token per token)
[ ] Reasoning tokens mostrati con <think>
[ ] FREE_ONLY filtra correttamente (suffisso + pricing)
[ ] Provider filter + inversion funziona
[ ] Prefix applicato e rimovibile
[ ] Fallbacks nel payload
[ ] Middle-out nel payload
[ ] Cache control su content lista
[ ] Retry su timeout, no retry su 4xx
[ ] Errori formattatati correttamente
[ ] Nessun secret nei log/messaggi
[ ] Campi OWUI interni rimossi dal payload
```
