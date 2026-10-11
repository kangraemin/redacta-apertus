### What goes wrong

We read every miss and every false positive on test (`docs/results/eval_full/errors.jsonl`).

**A bug the test set exposed.** The first full run gave {{R_FULL_V1}} recall. 41 of its 106 misses had one cause: Apertus labelled the party *recourant(e)*, and our check for public roles matched the substring *cour* (court) inside that word, so the party was kept. We fixed that one line (`role_redacts` in `src/anonymizer/llm.py`) and scored again with the same, cached Apertus answers. Because the bug was found on test, we also report the dev split, which played no part in the fix: {{R_DEV}} recall, {{PROT_DEV}} of protected names redacted. Both test runs are in `docs/results/` (`eval_full_before_fix/`).

**The remaining 55 misses on test:**

- *Private doctors (14).* "Dr. med. Manuela Steiner", "le docteur Luc Mercier": the title in front makes the pipeline treat the doctor as an official. Swiss courts usually remove a private doctor's name. These should go to *you decide*, not *kept*.
- *Lawyers the court had anonymised (17).* Now and then the court removes a lawyer's name too, when it would point to the client (`à Me A.________`). Our refill turns these into gold strings, while Redacta keeps every lawyer by design. The clerk has to catch these; a rule cannot.
- *Names the refill put in odd places (11).* The placeholder sometimes stood for a hospital, a company or a place ("Hôpital Camille Tissot", "in Urs Moser"), and Apertus did not list a person's name there. Part of this group is noise in our benchmark rather than a real leak.
- *Place names (10).* We inserted a town or street where the court had removed one ("un immeuble sis à Sion"). Neither Apertus nor the rules look for these.
- *Other (3):* a doctor labelled as an authority, a party read as a public service, a company read as the appellant.

**81 false positives.** They publish nothing wrong but cost the clerk a click each: courts and offices missing from our public-body list (47, e.g. *Chambre de surveillance*, *Sicherheitsdirektion*), role words read as names (19, e.g. *Gesuchstellerin*), judges or lawyers named later without a title (9, e.g. *Aubry Girardin*), and 6 addresses or dates.
