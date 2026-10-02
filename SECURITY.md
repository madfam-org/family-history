# Security

> Boundary checkpoint (2026-10-01): public policy. Report privately; never post a vulnerability
> or someone's family data in a public issue.

Please report vulnerabilities through GitHub's private vulnerability reporting for this
repository: the "Report a vulnerability" button under the Security tab. We acknowledge reports
within three business days.

What we treat as highest severity:

- **Exposure of a living person.** Any path that shows a living person, or a sensitive fact about
  one, outside their family space. That includes public pages, exports, search, logs and error
  messages.
- **Cross-family access.** Any request that reads or writes another family space's data
  (row-level security bypass).
- **Auth bypass.** Any route that answers without a valid Janua RS256 token of the right audience,
  or an app that starts with auth disabled outside `FH_ENV=local|test`.
- **Media leakage.** A media object reachable without a short-lived presigned URL, or served with
  its original location metadata.
- **Credential exposure.** Any secret in a commit, log, URL or response.

Requests from people who want to be removed from a family tree are not security reports. They are
privacy requests, handled through the product's «Quítame de este árbol» flow.
