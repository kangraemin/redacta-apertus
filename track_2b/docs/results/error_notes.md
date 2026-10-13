### What goes wrong

We read every miss and every false positive on test (`docs/results/eval_full/errors.jsonl`).

**A bug the test set exposed.** The first full run gave {{R_FULL_V1}} recall. 41 of its 106 misses had one cause: Apertus labelled the party *recourant(e)*, and our check for public roles matched the substring *cour* (court) inside that word, so the party was kept. We fixed that one line (`role_redacts` in `src/anonymizer/llm.py`) and scored again with the same, cached Apertus answers. Because the bug was found on test, we also reported the dev split, which played no part in that fix: {{R_DEV_V1}} recall, {{PROT_DEV_V1}} of protected names redacted. Both test runs are in `docs/results/` (`eval_full_before_fix/`).

**Two fixes made on dev only.** After that run we read the 36 dev decisions and changed two things, without looking at test again: (1) Apertus returned doctors with their title attached ("Dr. med. Francesca Grassi", "docteur Julien Berset"), and our checks then dropped the name. Medical titles are now stripped like other titles, and a doctor the model would keep goes to *you decide* instead, because courts usually remove a private doctor's name but may keep an insurer's medical adviser. (2) Chambers, directorates and secretariats (*Kammer*, *Chambre*, *Camera*, *-direktion*, *Sekretariat* ...) were added to the public-body list, and a lone role word (*Vermieterin*) is no longer read as a name. On dev, recall went from {{R_DEV_V1}} to {{R_DEV}} and precision from {{P_DEV_V1}} to {{P_DEV}}. We then scored test once: recall {{R_FULL_V2}} → {{R_FULL}}, precision {{P_FULL_V2}} → {{P_FULL}}, judge and lawyer names wrongly removed unchanged at {{PROT_FULL}}. No test decision got a new miss or a new false positive. The run before these fixes is in `docs/results/eval_full_before_dev_fixes/`.

**The remaining {{MISS_N}} misses on test:**

- *Lawyers the court had anonymised (17).* Now and then the court removes a lawyer's name too, when it would point to the client (`à Me A.________`). Our refill turns these into gold strings, while Redacta keeps every lawyer by design. The clerk has to catch these; a rule cannot.
- *Names the refill put in odd places (11).* The placeholder sometimes stood for a hospital, a company or a place ("Hôpital Camille Tissot", "in Urs Moser"), and Apertus did not list a person's name there. Part of this group is noise in our benchmark rather than a real leak.
- *Place names (10).* We inserted a town or street where the court had removed one ("un immeuble sis à Sion"). Neither Apertus nor the rules look for these.
- *Other (3):* a doctor written "la Dre" and labelled as an authority, a party read as a public service, a company read only in part.

**{{FP_N}} false positives** (81 before the dev fixes). They publish nothing wrong but cost the clerk a click each: public bodies still missing from our list (26, e.g. *Verwaltungsrekurskommission*, *État de Vaud*, *Unisanté*), common words read as names (7, e.g. *Gartenbaufirma*), judges or lawyers named later without a title (9, e.g. *Aubry Girardin*), and 5 addresses, dates or places.
