# Lezioni

- Unit test verdi non verificano il salvataggio OWUI: riprodurre create/update su container pulito e acquisire log backend prima di dichiarare risolta un'incompatibilità.
- Cambio convenzione changelog: allineare CONTRIBUTING.md e template PR; sezione Unreleased solo con voci pendenti.
- Audit OpenRouter: confrontare schema/discovery live oltre ai mock; `/models` pubblico non valida chiavi, usare `/key`, e applicare policy/capability per endpoint.
- Filtro free: token prompt/completion a zero non bastano; controllare anche tariffe immagine/audio/request, altrimenti modelli media a pagamento risultano gratuiti.
- Audit OWUI: usare schemi e wrapper runtime reali; `ModelForm` riscrive campi default e un wrapper async può eseguire un tool sync sull'event loop.
- Video `0/0` su `/models` non significa gratis: tariffe per secondo sono SKU separati di `/videos/models`.
- OWUI scarta in silenzio i profile image non accettati (SVG data URI) ma `update_model_by_id` restituisce comunque la riga: verificare la persistenza dall'esito, non dal non-None; provare sync su copia del DB reale della versione OWUI in produzione.
