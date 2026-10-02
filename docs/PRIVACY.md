# Privacy by design

> Last Updated: 2026-10-01
>
> Boundary checkpoint (2026-10-01): public design rules. The privacy notice
> (aviso de privacidad) shown to families is drafted separately and is reviewed by counsel
> before launch.

The platform holds the most personal data there is: family relationships, religious records,
causes of death, voices and photos of people who never signed up. Mexico's Ley Federal de
Protección de Datos Personales en Posesión de los Particulares (DOF 2025-03-20) treats religion,
health, genetic and ethnic data as sensitive. Misuse carries fines that double for sensitive
data. These rules are product behaviour, not policy text.

1. **Living people are private by default.**
   - Anyone not proven dead (no death event with evidence) is treated as living:
     - when born within the last 110 years;
     - or with no known birth date.
   - A living person is visible only inside their family space. Nothing about a living person is
     ever public.
2. **Facts carry a sensitivity class.** The classes are religion, health, genetic, ethnicity,
   sexual and political.
   - Every sacramental event (bautismo, confirmación, primera comunión, matrimonio religioso)
     defaults to religion.
   - Cause of death and medical notes default to health.
3. **Sensitive facts about living people stay with the contributor** until the person gives
   express consent, authenticated through Janua.
4. **«Quítame de este árbol».** Any living person can ask to be hidden or removed from a tree,
   whether or not they have an account.
5. **ARCO requests are answered within 20 business days.** These are the rights of access,
   rectification, cancellation and opposition. Export doubles as access and portability.
6. **Automated hints and matching are opt-in** per family space, and any person can opt out.
7. **Accounts are for adults.** Minors appear only as private data subjects inside a family's tree.
8. **Out of scope, permanently:**
   - DNA or genetic data;
   - CURP collection;
   - health-risk inference;
   - data sale;
   - training models on family content;
   - voice cloning or face animation of real people.
9. **Media.**
   - Originals are immutable and stored in a private bucket, reached only through short-lived
     presigned URLs.
   - Location metadata (EXIF/GPS) is stripped from every served copy.
   - AI-modified images carry a visible «Modificada con IA» label and provenance, and are never
     used as evidence.
10. **AI** runs only through the MADFAM inference gateway at `restricted` or `confidential`
    sensitivity, and the feature disappears when the gateway cannot serve that level. AI output
    is a suggestion, never a fact.
