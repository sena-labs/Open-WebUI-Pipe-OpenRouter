# Lezioni

- Unit test verdi non verificano il salvataggio OWUI: riprodurre create/update su container pulito e acquisire log backend prima di dichiarare risolta un'incompatibilità.
- Cambio convenzione changelog: allineare CONTRIBUTING.md e template PR; sezione Unreleased solo con voci pendenti.
- Audit OpenRouter: confrontare schema/discovery live oltre ai mock; `/models` pubblico non valida chiavi, usare `/key`, e applicare policy/capability per endpoint.
- Filtro free: token prompt/completion a zero non bastano; controllare anche tariffe immagine/audio/request, altrimenti modelli media a pagamento risultano gratuiti.
