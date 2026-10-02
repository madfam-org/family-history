# Aviso de privacidad (counsel-reviewed text only)

This folder holds the privacy notice shown at `/<locale>/aviso-de-privacidad`, one plain-text
file per reviewed version and locale: `<FH_AVISO_VERSION>.es.txt` and `<FH_AVISO_VERSION>.en.txt`.

- Only text reviewed by counsel goes here. Engineers and agents never write legal text.
- Format: paragraphs separated by a blank line; a line starting with `# ` is a heading.
- Until `FH_AVISO_VERSION` is set **and** the matching file exists, the page says
  «Aviso de privacidad en revisión» and the waitlist form does not render.
